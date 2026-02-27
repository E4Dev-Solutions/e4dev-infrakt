"""GitHub webhook receiver for self-updating the infrakt container.

Uses a sidecar container pattern to avoid the restart-from-within deadlock.
"""

import hashlib
import hmac
import logging
import os
import subprocess
import threading

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter(tags=["self-update"])

logger = logging.getLogger("infrakt.self_update")

# The compose file path inside the container — matches the mount in
# docker-compose.prod.yml on the host at /opt/infrakt/.
_COMPOSE_FILE = os.environ.get("COMPOSE_FILE", "/opt/infrakt/docker-compose.prod.yml")
_COMPOSE_DIR = os.path.dirname(_COMPOSE_FILE) or "/opt/infrakt"
_IMAGE = os.environ.get("INFRAKT_IMAGE", "ghcr.io/e4dev-solutions/e4dev-infrakt:latest")


def _verify_signature(payload: bytes, signature: str, secret: str) -> bool:
    """Verify GitHub's X-Hub-Signature-256 HMAC."""
    expected = "sha256=" + hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


def _do_update() -> None:
    """Pull the latest image and restart via a sidecar container.

    We cannot run ``docker compose up -d`` from inside the very container
    being replaced — Docker stops this container first, killing the process
    before it can start the new one (leaving it stuck in ``Created`` state).

    Instead we: 1) pull the new image, then 2) spawn a short-lived sidecar
    container that waits a few seconds and runs ``docker compose up -d``.
    The sidecar is independent and survives the main container's restart.
    """
    try:
        logger.info("Pulling latest image...")
        subprocess.run(
            ["docker", "compose", "-f", _COMPOSE_FILE, "pull"],
            check=True,
            capture_output=True,
            text=True,
            timeout=300,
        )

        # Remove any leftover updater container from a previous run.
        subprocess.run(
            ["docker", "rm", "-f", "infrakt-updater"],
            capture_output=True,
            text=True,
        )

        logger.info("Spawning updater sidecar to restart container...")
        subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "-d",
                "--name",
                "infrakt-updater",
                "--entrypoint",
                "sh",
                "-v",
                "/var/run/docker.sock:/var/run/docker.sock",
                "-v",
                f"{_COMPOSE_DIR}:{_COMPOSE_DIR}:ro",
                "-w",
                _COMPOSE_DIR,
                _IMAGE,
                "-c",
                "sleep 3 && docker compose -f "
                f"{_COMPOSE_FILE} up -d --force-recreate --remove-orphans",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        logger.info("Updater sidecar launched — container will restart shortly.")
    except subprocess.CalledProcessError as exc:
        logger.error("Self-update failed: %s\n%s", exc, exc.stderr)
    except Exception as exc:
        logger.error("Self-update error: %s", exc)


@router.post("/self-update")
async def self_update(
    request: Request,
    x_hub_signature_256: str | None = Header(None),
    x_github_event: str | None = Header(None),
) -> dict[str, str]:
    """Receive a GitHub webhook push event and trigger a self-update.

    GitHub must be configured with a webhook secret that matches the
    ``GITHUB_WEBHOOK_SECRET`` environment variable.
    """
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(503, "GITHUB_WEBHOOK_SECRET not configured")

    # --- Verify signature -----------------------------------------------------
    body = await request.body()

    if not x_hub_signature_256:
        raise HTTPException(401, "Missing X-Hub-Signature-256 header")

    if not _verify_signature(body, x_hub_signature_256, secret):
        raise HTTPException(403, "Invalid signature")

    # --- Check event type -----------------------------------------------------
    if x_github_event == "ping":
        return {"status": "pong"}

    if x_github_event != "push":
        return {"status": "ignored", "reason": f"event={x_github_event}"}

    # --- Check branch ---------------------------------------------------------
    import json

    payload = json.loads(body)
    ref = payload.get("ref", "")
    if ref != "refs/heads/main":
        return {"status": "ignored", "reason": f"ref={ref}"}

    # --- Trigger update in background ----------------------------------------
    threading.Thread(target=_do_update, daemon=True).start()

    return {"status": "updating"}
