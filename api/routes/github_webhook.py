"""GitHub push webhook receiver for auto-deploy."""

from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from cli.core.database import get_session, init_db
from cli.models.app import App

router = APIRouter(prefix="/deploy", tags=["deploy"])
logger = logging.getLogger(__name__)


@router.post("/github-webhook")
async def github_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Receive GitHub push webhooks and trigger auto-deploys.

    This endpoint uses GitHub HMAC signature verification (per-app
    ``webhook_secret``) instead of the platform API key.
    """
    event = request.headers.get("X-GitHub-Event", "")
    if event == "ping":
        return {"message": "pong"}
    if event != "push":
        return {"message": f"Ignored event: {event}"}

    sig_header = request.headers.get("X-Hub-Signature-256", "")
    if not sig_header:
        raise HTTPException(400, "Missing X-Hub-Signature-256 header")

    body = await request.body()
    payload = await request.json()

    ref = payload.get("ref", "")
    branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ""
    clone_url = payload.get("repository", {}).get("clone_url", "")

    if not branch or not clone_url:
        return {"message": "Missing ref or repository in payload"}

    init_db()
    with get_session() as session:
        apps = session.query(App).filter(App.git_repo == clone_url, App.branch == branch).all()
        if not apps:
            return {"message": "No matching app for this repo/branch"}

        for app_obj in apps:
            if not app_obj.webhook_secret:
                continue

            expected_sig = (
                "sha256="
                + hmac.new(app_obj.webhook_secret.encode(), body, hashlib.sha256).hexdigest()
            )
            if not hmac.compare_digest(sig_header, expected_sig):
                continue

            if not app_obj.auto_deploy:
                return {"message": f"Auto-deploy disabled for '{app_obj.name}'"}

            app_name = app_obj.name
            background_tasks.add_task(_trigger_deploy, app_name)
            return {"message": f"Deploy triggered for '{app_name}'"}

    return {"message": "No matching app for this repo/branch"}


def _trigger_deploy(app_name: str) -> None:
    """Trigger a deploy using the existing deploy machinery."""
    from cli.core.crypto import env_content_for_app
    from cli.core.deployer import deploy_app
    from cli.core.proxy_manager import add_domain
    from cli.core.ssh import SSHClient
    from cli.core.webhook_sender import fire_webhooks
    from cli.models.deployment import Deployment

    init_db()
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == app_name).first()
        if not app_obj:
            return
        srv = app_obj.server
        dep = Deployment(app_id=app_obj.id, status="in_progress")
        session.add(dep)
        session.flush()
        dep_id = dep.id
        app_id = app_obj.id
        app_data = {
            "port": app_obj.port,
            "git_repo": app_obj.git_repo,
            "branch": app_obj.branch,
            "image": app_obj.image,
            "domain": app_obj.domain,
            "cpu_limit": app_obj.cpu_limit,
            "memory_limit": app_obj.memory_limit,
        }
        ssh_data = {
            "host": srv.host,
            "user": srv.user,
            "port": srv.port,
            "key_path": srv.ssh_key_path,
        }

    ssh = SSHClient(
        host=ssh_data["host"],
        user=ssh_data["user"],
        port=ssh_data["port"],
        key_path=ssh_data.get("key_path"),
    )
    try:
        with ssh:
            ssh.run("docker network create infrakt 2>/dev/null || true")
            env_content = env_content_for_app(app_id)
            result = deploy_app(
                ssh,
                app_name,
                git_repo=app_data.get("git_repo"),
                branch=app_data.get("branch", "main"),
                image=app_data.get("image"),
                port=app_data.get("port", 3000),
                env_content=env_content,
                cpu_limit=app_data.get("cpu_limit"),
                memory_limit=app_data.get("memory_limit"),
            )
            domain = app_data.get("domain")
            if domain:
                add_domain(ssh, domain, app_data.get("port", 3000))

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
        fire_webhooks("deploy.success", {"app": app_name, "deployment_id": dep_id})
    except Exception as exc:
        logger.exception("Webhook deploy error for %s", app_name)
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
