"""Simplified deploy trigger endpoint for CI/CD."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging
import threading
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Security
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

from api.auth import get_or_create_api_key
from api.log_broadcaster import broadcaster
from cli.core.crypto import env_content_for_app
from cli.core.database import get_session, init_db
from cli.core.deploy_keys import validate_deploy_key
from cli.core.deployer import deploy_app
from cli.core.exceptions import SSHConnectionError
from cli.core.proxy_manager import add_domain
from cli.core.ssh import SSHClient
from cli.core.webhook_sender import fire_webhooks
from cli.models.app import App
from cli.models.deployment import Deployment

router = APIRouter(prefix="/deploy", tags=["deploy"])
logger = logging.getLogger(__name__)

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


class DeployTrigger(BaseModel):
    """Request body for triggering a deployment."""

    app_name: str = Field(..., min_length=1, max_length=100)
    image: str | None = None
    branch: str | None = None


def _require_api_or_deploy_key(
    api_key: str | None = Security(_api_key_header),
) -> str:
    """Accept either the main API key or a valid deploy key."""
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")

    expected = get_or_create_api_key()
    if hmac.compare_digest(
        hashlib.sha256(api_key.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    ):
        return api_key

    dk = validate_deploy_key(api_key)
    if dk is not None:
        return api_key

    raise HTTPException(status_code=403, detail="Invalid API key or deploy key")


@router.post("")
async def trigger_deploy(
    body: DeployTrigger,
    background_tasks: BackgroundTasks,
    _key: str = Security(_require_api_or_deploy_key),
) -> dict[str, str | int]:
    """Trigger a deployment from CI/CD.

    Accepts either the main API key or a restricted deploy key generated
    with `infrakt ci generate-key`.
    """
    init_db()
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == body.app_name).first()
        if not app_obj:
            raise HTTPException(404, f"App '{body.app_name}' not found")

        srv = app_obj.server
        dep = Deployment(app_id=app_obj.id, status="in_progress")
        session.add(dep)
        session.flush()

        dep_id = dep.id
        app_id = app_obj.id
        app_name = app_obj.name

        # Extract and type all required values
        ssh_host: str = srv.host
        ssh_user: str = srv.user
        ssh_port: int = srv.port
        ssh_key: str | None = srv.ssh_key_path

        app_port: int = app_obj.port
        app_git_repo: str | None = app_obj.git_repo
        app_branch: str = body.branch or app_obj.branch
        app_image: str | None = body.image or app_obj.image
        app_domain: str | None = app_obj.domain
        app_cpu: str | None = app_obj.cpu_limit
        app_mem: str | None = app_obj.memory_limit

    loop = asyncio.get_running_loop()
    broadcaster.register(dep_id, loop)

    def _do_deploy() -> None:
        def _on_log(line: str) -> None:
            broadcaster.publish(dep_id, line)

        ssh = SSHClient(
            host=ssh_host,
            user=ssh_user,
            port=ssh_port,
            key_path=ssh_key,
        )
        try:
            with ssh:
                ssh.run("docker network create infrakt 2>/dev/null || true")
                env_content = env_content_for_app(app_id)
                result = deploy_app(
                    ssh,
                    app_name,
                    git_repo=app_git_repo,
                    branch=app_branch,
                    image=app_image,
                    port=app_port,
                    env_content=env_content,
                    log_fn=_on_log,
                    cpu_limit=app_cpu,
                    memory_limit=app_mem,
                )
                if app_domain:
                    add_domain(ssh, app_domain, app_port, app_name=name)

            with get_session() as session:
                dep = session.query(Deployment).filter(Deployment.id == dep_id).first()
                if dep:
                    dep.status = "success"
                    dep.log = result.log
                    dep.commit_hash = result.commit_hash
                    dep.image_used = result.image_used
                    dep.finished_at = datetime.utcnow()
                a = session.query(App).filter(App.id == app_id).first()
                if a:
                    a.status = "running"
            fire_webhooks(
                "deploy.success",
                {"app": app_name, "deployment_id": dep_id},
            )
        except (SSHConnectionError, Exception) as exc:
            logger.exception("CI deploy error for %s", app_name)
            broadcaster.publish(dep_id, f"[ERROR] {exc}")
            with get_session() as session:
                dep = session.query(Deployment).filter(Deployment.id == dep_id).first()
                if dep:
                    dep.status = "failed"
                    dep.log = str(exc)
                    dep.finished_at = datetime.utcnow()
                a = session.query(App).filter(App.id == app_id).first()
                if a:
                    a.status = "error"
            fire_webhooks(
                "deploy.failure",
                {"app": app_name, "deployment_id": dep_id, "error": str(exc)},
            )
        finally:
            broadcaster.finish(dep_id)
            threading.Timer(300, broadcaster.cleanup, args=[dep_id]).start()

    background_tasks.add_task(_do_deploy)
    return {"message": f"Deployment started for '{body.app_name}'", "deployment_id": dep_id}
