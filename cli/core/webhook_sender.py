"""Fire-and-forget webhook delivery."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

VALID_EVENTS = frozenset(
    [
        "deploy.success",
        "deploy.failure",
        "backup.complete",
        "backup.restore",
        "health.down",
        "health.up",
    ]
)


def build_payload(event: str, data: dict[str, object]) -> dict[str, object]:
    """Build a webhook payload with event type and timestamp."""
    return {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": data,
    }


def _format_message(payload: dict[str, object]) -> str:
    """Build a human-readable notification message."""
    event = str(payload.get("event", "unknown"))
    data = payload.get("data", {})
    if not isinstance(data, dict):
        data = {}
    app = str(data.get("app", data.get("database", "unknown")))
    server = str(data.get("server", ""))

    messages = {
        "deploy.success": f"Deploy of {app} succeeded" + (f" on {server}" if server else ""),
        "deploy.failure": f"Deploy of {app} failed" + (f" on {server}" if server else ""),
        "backup.complete": f"Backup of {app} completed",
        "backup.restore": f"Restore of {app} completed",
        "health.down": f"{app} is down",
        "health.up": f"{app} is back up",
    }
    return f"[infrakt] {messages.get(event, event)}"


def deliver_webhook(
    url: str,
    secret: str | None,
    payload: dict[str, object],
    timeout: int = 10,
    channel_type: str = "custom",
) -> None:
    """HTTP POST the payload to url. Logs errors — never raises."""
    if channel_type == "slack":
        body = json.dumps({"text": _format_message(payload)}).encode()
    elif channel_type == "discord":
        body = json.dumps({"content": _format_message(payload)}).encode()
    else:
        body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "infrakt-webhooks/0.1",
        },
    )
    if secret and channel_type == "custom":
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        req.add_header("X-Webhook-Signature", f"sha256={sig}")
    try:
        urllib.request.urlopen(req, timeout=timeout)  # noqa: S310
    except (urllib.error.URLError, OSError) as exc:
        logger.warning("Webhook delivery to %s failed: %s", url, exc)


def fire_webhooks(event: str, data: dict[str, object]) -> None:
    """Load matching webhooks from DB and fire each."""
    from cli.core.database import get_session
    from cli.models.webhook import Webhook

    payload = build_payload(event, data)
    with get_session() as session:
        hooks = session.query(Webhook).all()
        targets = [
            (h.url, h.secret, getattr(h, "channel_type", "custom"))
            for h in hooks
            if event in h.events.split(",")
        ]

    for url, secret, ch_type in targets:
        deliver_webhook(url, secret, payload, channel_type=ch_type)
