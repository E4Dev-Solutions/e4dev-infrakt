"""App management API routes."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import threading
from collections.abc import AsyncIterator
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import joinedload

from api.log_broadcaster import broadcaster
from api.schemas import (
    AppCreate,
    AppDependencyCreate,
    AppDependencyOut,
    AppHealth,
    AppHealthCheckResult,
    AppLogs,
    AppOut,
    AppUpdate,
    ContainerHealth,
    DeploymentOut,
    ScaleInput,
)
from cli.core.crypto import env_content_for_app
from cli.core.github import create_repo_webhook, get_github_token
from cli.core.database import get_session, init_db
from cli.core.deployer import (
    deploy_app,
    destroy_app,
    get_container_health,
    get_logs,
    reconcile_app_status,
    restart_app,
    stop_app,
    stream_logs,
)
from cli.core.exceptions import SSHConnectionError
from cli.core.proxy_manager import add_domain, remove_domain
from cli.core.ssh import SSHClient
from cli.core.webhook_sender import fire_webhooks
from cli.models.app import App
from cli.models.app_dependency import AppDependency
from cli.models.deployment import Deployment
from cli.models.server import Server

router = APIRouter(prefix="/apps", tags=["apps"])
logger = logging.getLogger(__name__)


def _ssh_for(srv: Server) -> SSHClient:
    return SSHClient.from_server(srv)


def _app_out(a: App, session: object | None = None) -> AppOut:
    """Build an AppOut from an App model, resolving dependencies if session is provided."""
    dep_names: list[str] = []
    if session is not None:
        deps = (
            session.query(AppDependency)  # type: ignore[attr-defined]
            .filter(AppDependency.app_id == a.id)
            .all()
        )
        for d in deps:
            dep_app = session.query(App).filter(App.id == d.depends_on_app_id).first()  # type: ignore[attr-defined]
            if dep_app:
                dep_names.append(dep_app.name)
    return AppOut(
        id=a.id,
        name=a.name,
        server_id=a.server_id,
        server_name=a.server.name,
        domain=a.domain,
        port=a.port,
        git_repo=a.git_repo,
        branch=a.branch,
        image=a.image,
        status=a.status,
        app_type=a.app_type,
        cpu_limit=a.cpu_limit,
        memory_limit=a.memory_limit,
        health_check_url=a.health_check_url,
        health_check_interval=a.health_check_interval,
        replicas=a.replicas,
        deploy_strategy=a.deploy_strategy,
        dependencies=dep_names,
        created_at=a.created_at,
        updated_at=a.updated_at,
    )


@router.get("", response_model=list[AppOut])
def list_apps(server: str | None = None) -> list[AppOut]:
    """List all apps, optionally filtered by server."""
    init_db()
    with get_session() as session:
        q = session.query(App).join(Server).options(joinedload(App.server))
        if server:
            q = q.filter(Server.name == server)
        apps = q.filter(~App.app_type.like("db:%")).order_by(Server.name, App.name).all()
        return [_app_out(a, session) for a in apps]


@router.post("", response_model=AppOut, status_code=201)
def create_app(body: AppCreate) -> AppOut:
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == body.server_name).first()
        if not srv:
            raise HTTPException(404, f"Server '{body.server_name}' not found")

        existing = session.query(App).filter(App.name == body.name, App.server_id == srv.id).first()
        if existing:
            raise HTTPException(400, f"App '{body.name}' already exists on '{body.server_name}'")

        app_type = "image" if body.image else "git" if body.git_repo else "compose"
        new_app = App(
            name=body.name,
            server_id=srv.id,
            domain=body.domain,
            port=body.port,
            git_repo=body.git_repo,
            branch=body.branch,
            image=body.image,
            app_type=app_type,
            status="stopped",
            cpu_limit=body.cpu_limit,
            memory_limit=body.memory_limit,
            health_check_url=body.health_check_url,
            health_check_interval=body.health_check_interval,
            replicas=body.replicas,
            deploy_strategy=body.deploy_strategy,
        )
        session.add(new_app)
        session.flush()

        return _app_out(new_app, session)


@router.put("/{name}", response_model=AppOut)
def update_app(name: str, body: AppUpdate, server: str | None = None) -> AppOut:
    """Update an app's configuration."""
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name).options(joinedload(App.server))
        if server:
            q = q.join(Server).filter(Server.name == server)
        app_obj = q.first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")

        if body.domain is not None:
            app_obj.domain = body.domain
        if body.port is not None:
            app_obj.port = body.port
        if body.git_repo is not None:
            app_obj.git_repo = body.git_repo
        if body.branch is not None:
            app_obj.branch = body.branch
        if body.image is not None:
            app_obj.image = body.image
        if body.cpu_limit is not None:
            app_obj.cpu_limit = body.cpu_limit
        if body.memory_limit is not None:
            app_obj.memory_limit = body.memory_limit
        if body.health_check_url is not None:
            app_obj.health_check_url = body.health_check_url
        if body.health_check_interval is not None:
            app_obj.health_check_interval = body.health_check_interval
        if body.replicas is not None:
            app_obj.replicas = body.replicas
        if body.deploy_strategy is not None:
            app_obj.deploy_strategy = body.deploy_strategy

        if body.image is not None or body.git_repo is not None:
            if app_obj.image:
                app_obj.app_type = "image"
            elif app_obj.git_repo:
                app_obj.app_type = "git"
            else:
                app_obj.app_type = "compose"

        session.flush()

        return _app_out(app_obj, session)


@router.post("/{name}/deploy")
async def deploy(
    name: str,
    request: Request,
    background_tasks: BackgroundTasks,
    server: str | None = None,
) -> dict[str, str | int]:
    init_db()
    base_url = str(request.base_url).rstrip("/")
    with get_session() as session:
        q = session.query(App).filter(App.name == name)
        if server:
            q = q.join(Server).filter(Server.name == server)
        app_obj = q.first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")

        srv = app_obj.server
        dep = Deployment(app_id=app_obj.id, status="in_progress")
        session.add(dep)
        session.flush()

        dep_id = dep.id
        app_id = app_obj.id
        app_data: dict[str, str | int | None] = {
            "port": app_obj.port,
            "git_repo": app_obj.git_repo,
            "branch": app_obj.branch,
            "image": app_obj.image,
            "domain": app_obj.domain,
            "cpu_limit": app_obj.cpu_limit,
            "memory_limit": app_obj.memory_limit,
            "replicas": app_obj.replicas,
            "deploy_strategy": app_obj.deploy_strategy,
            "health_check_url": app_obj.health_check_url,
            "health_check_interval": app_obj.health_check_interval,
        }
        ssh_data: dict[str, str | int | None] = {
            "host": srv.host,
            "user": srv.user,
            "port": srv.port,
            "key_path": srv.ssh_key_path,
        }

    # Register for live log streaming before starting the background task.
    loop = asyncio.get_running_loop()
    broadcaster.register(dep_id, loop)

    def _do_deploy() -> None:
        def _on_log(line: str) -> None:
            broadcaster.publish(dep_id, line)

        ssh = SSHClient(
            host=ssh_data.get("host", ""),  # type: ignore[arg-type]
            user=ssh_data.get("user", "root"),  # type: ignore[arg-type]
            port=ssh_data.get("port", 22),  # type: ignore[arg-type]
            key_path=ssh_data.get("key_path"),  # type: ignore[arg-type]
        )
        try:
            with ssh:
                ssh.run("docker network create infrakt 2>/dev/null || true")
                env_content = env_content_for_app(app_id)
                git_repo = app_data.get("git_repo")
                if not isinstance(git_repo, (str, type(None))):
                    git_repo = None
                branch = app_data.get("branch")
                if not isinstance(branch, str):
                    branch = "main"
                image = app_data.get("image")
                if not isinstance(image, (str, type(None))):
                    image = None
                port = app_data.get("port")
                if not isinstance(port, int):
                    port = 3000
                cpu_limit = app_data.get("cpu_limit")
                if not isinstance(cpu_limit, (str, type(None))):
                    cpu_limit = None
                memory_limit = app_data.get("memory_limit")
                if not isinstance(memory_limit, (str, type(None))):
                    memory_limit = None
                replicas = app_data.get("replicas")
                if not isinstance(replicas, int):
                    replicas = 1
                deploy_strategy = app_data.get("deploy_strategy")
                if not isinstance(deploy_strategy, str):
                    deploy_strategy = "restart"
                health_check_url = app_data.get("health_check_url")
                if not isinstance(health_check_url, (str, type(None))):
                    health_check_url = None
                health_check_interval = app_data.get("health_check_interval")
                if not isinstance(health_check_interval, (int, type(None))):
                    health_check_interval = None
                result = deploy_app(
                    ssh,
                    name,
                    git_repo=git_repo,
                    branch=branch,
                    image=image,
                    port=port,
                    env_content=env_content,
                    log_fn=_on_log,
                    cpu_limit=cpu_limit,
                    memory_limit=memory_limit,
                    replicas=replicas,
                    deploy_strategy=deploy_strategy,
                    health_check_url=health_check_url,
                    health_check_interval=health_check_interval,
                )
                domain = app_data.get("domain")
                if domain:
                    if not isinstance(domain, str):
                        domain = str(domain)
                    add_domain(ssh, domain, port)

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

            # Auto-create GitHub webhook on first deploy
            original_git_repo = app_data.get("git_repo")
            if original_git_repo and "github.com" in (original_git_repo or ""):
                gh_token = get_github_token()
                if gh_token:
                    with get_session() as session:
                        a = session.query(App).filter(App.id == app_id).first()
                        if a and not a.webhook_secret:
                            webhook_secret = secrets.token_urlsafe(32)
                            # Parse owner/repo from git URL
                            parts = (
                                (original_git_repo or "")
                                .replace("https://github.com/", "")
                                .replace(".git", "")
                                .split("/")
                            )
                            if len(parts) >= 2:
                                owner, repo_name = parts[0], parts[1]
                                hook_id = create_repo_webhook(
                                    gh_token,
                                    owner,
                                    repo_name,
                                    f"{base_url}/api/deploy/github-webhook",
                                    webhook_secret,
                                )
                                if hook_id:
                                    a.webhook_secret = webhook_secret
                                    _on_log(
                                        f"Auto-created GitHub webhook for {owner}/{repo_name}"
                                    )

            fire_webhooks(
                "deploy.success",
                {
                    "app": name,
                    "deployment_id": dep_id,
                    "commit_hash": result.commit_hash,
                    "image_used": result.image_used,
                },
            )
        except SSHConnectionError as exc:
            logger.error("Deployment SSH error for %s: %s", name, exc)
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
                {
                    "app": name,
                    "deployment_id": dep_id,
                    "error": str(exc),
                },
            )
        except Exception as exc:
            logger.exception("Unexpected deployment error for %s", name)
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
                {
                    "app": name,
                    "deployment_id": dep_id,
                    "error": str(exc),
                },
            )
        finally:
            broadcaster.finish(dep_id)
            # Clean up broadcaster state after 5 minutes
            threading.Timer(300, broadcaster.cleanup, args=[dep_id]).start()

    background_tasks.add_task(_do_deploy)
    return {"message": f"Deployment started for '{name}'", "deployment_id": dep_id}


@router.post("/{name}/rollback")
async def rollback(
    name: str,
    background_tasks: BackgroundTasks,
    deployment_id: int | None = None,
    server: str | None = None,
) -> dict[str, str | int]:
    """Roll back an app to a previous successful deployment."""
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name)
        if server:
            q = q.join(Server).filter(Server.name == server)
        app_obj = q.first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")

        app_id = app_obj.id
        srv = app_obj.server

        # Find target deployment
        if deployment_id:
            target = (
                session.query(Deployment)
                .filter(
                    Deployment.id == deployment_id,
                    Deployment.app_id == app_id,
                    Deployment.status == "success",
                )
                .first()
            )
            if not target:
                raise HTTPException(
                    404,
                    f"No successful deployment #{deployment_id} found for '{name}'",
                )
        else:
            successes = (
                session.query(Deployment)
                .filter(Deployment.app_id == app_id, Deployment.status == "success")
                .order_by(Deployment.started_at.desc())
                .limit(2)
                .all()
            )
            if len(successes) < 2:
                raise HTTPException(
                    404,
                    f"No previous successful deployment to roll back to for '{name}'",
                )
            target = successes[1]

        pinned_commit = target.commit_hash
        pinned_image = target.image_used
        target_dep_id = target.id

        app_data: dict[str, str | int | None] = {
            "port": app_obj.port,
            "git_repo": app_obj.git_repo,
            "branch": app_obj.branch,
            "image": pinned_image or app_obj.image,
            "domain": app_obj.domain,
        }
        ssh_data: dict[str, str | int | None] = {
            "host": srv.host,
            "user": srv.user,
            "port": srv.port,
            "key_path": srv.ssh_key_path,
        }

        # Create new deployment record for rollback
        dep = Deployment(app_id=app_id, status="in_progress")
        session.add(dep)
        session.flush()
        dep_id = dep.id

    loop = asyncio.get_running_loop()
    broadcaster.register(dep_id, loop)

    def _do_rollback() -> None:
        def _on_log(line: str) -> None:
            broadcaster.publish(dep_id, line)

        ssh = SSHClient(
            host=ssh_data.get("host", ""),  # type: ignore[arg-type]
            user=ssh_data.get("user", "root"),  # type: ignore[arg-type]
            port=ssh_data.get("port", 22),  # type: ignore[arg-type]
            key_path=ssh_data.get("key_path"),  # type: ignore[arg-type]
        )
        try:
            with ssh:
                ssh.run("docker network create infrakt 2>/dev/null || true")
                env_content = env_content_for_app(app_id)
                git_repo = app_data.get("git_repo")
                if not isinstance(git_repo, (str, type(None))):
                    git_repo = None
                branch = app_data.get("branch")
                if not isinstance(branch, str):
                    branch = "main"
                image = app_data.get("image")
                if not isinstance(image, (str, type(None))):
                    image = None
                port = app_data.get("port")
                if not isinstance(port, int):
                    port = 3000
                result = deploy_app(
                    ssh,
                    name,
                    git_repo=git_repo,
                    branch=branch,
                    image=image,
                    port=port,
                    env_content=env_content,
                    log_fn=_on_log,
                    pinned_commit=pinned_commit,
                )
                domain = app_data.get("domain")
                if domain:
                    if not isinstance(domain, str):
                        domain = str(domain)
                    add_domain(ssh, domain, port)

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
                {
                    "app": name,
                    "deployment_id": dep_id,
                    "commit_hash": result.commit_hash,
                    "image_used": result.image_used,
                },
            )
        except Exception as exc:
            logger.exception("Rollback error for %s", name)
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
                {
                    "app": name,
                    "deployment_id": dep_id,
                    "error": str(exc),
                },
            )
        finally:
            broadcaster.finish(dep_id)
            threading.Timer(300, broadcaster.cleanup, args=[dep_id]).start()

    background_tasks.add_task(_do_rollback)
    return {
        "message": f"Rolling back '{name}' to deployment #{target_dep_id}",
        "deployment_id": dep_id,
    }


@router.get("/{name}/logs", response_model=AppLogs)
def app_logs(name: str, server: str | None = None, lines: int = 100) -> AppLogs:
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name)
        if server:
            q = q.join(Server).filter(Server.name == server)
        app_obj = q.first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        ssh = _ssh_for(app_obj.server)

    try:
        with ssh:
            output = get_logs(ssh, name, lines=lines)
    except SSHConnectionError as exc:
        raise HTTPException(502, str(exc))

    return AppLogs(app_name=name, logs=output)


@router.get("/{name}/logs/stream")
async def stream_app_logs(name: str, lines: int = 100) -> StreamingResponse:
    """Stream live container logs via Server-Sent Events."""
    init_db()
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == name).first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        ssh = _ssh_for(app_obj.server)

    ssh.connect()
    loop = asyncio.get_running_loop()
    _sentinel = object()

    def _next_line(gen):  # noqa: ANN001, ANN202
        return next(gen, _sentinel)

    async def _generate() -> AsyncIterator[str]:
        try:
            gen = stream_logs(ssh, name, lines=lines)
            while True:
                line = await loop.run_in_executor(None, _next_line, gen)
                if line is _sentinel:
                    break
                yield f"data: {json.dumps({'line': line})}\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            ssh.close()

    return StreamingResponse(
        _generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/{name}/deployments", response_model=list[DeploymentOut])
def app_deployments(name: str) -> list[DeploymentOut]:
    init_db()
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == name).first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        deps = (
            session.query(Deployment)
            .filter(Deployment.app_id == app_obj.id)
            .order_by(Deployment.started_at.desc())
            .limit(20)
            .all()
        )
        return [DeploymentOut.model_validate(d) for d in deps]


@router.get("/{name}/deployments/{dep_id}/logs/stream")
async def stream_deployment_logs(name: str, dep_id: int) -> StreamingResponse:
    """Stream deployment logs via Server-Sent Events."""
    init_db()

    # Verify the deployment exists and belongs to this app.
    with get_session() as session:
        app_obj: App | None = session.query(App).filter(App.name == name).first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        dep: Deployment | None = (
            session.query(Deployment)
            .filter(Deployment.id == dep_id, Deployment.app_id == app_obj.id)
            .first()
        )
        if not dep:
            raise HTTPException(404, f"Deployment {dep_id} not found")

        dep_status = dep.status
        stored_log = dep.log

    sse_headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    # If the deployment is already finished, replay the stored log and close.
    if dep_status in ("success", "failed") and stored_log:

        async def _finished_stream() -> AsyncIterator[str]:
            for line in stored_log.splitlines():
                yield f"data: {json.dumps({'line': line})}\n\n"
            yield f"data: {json.dumps({'done': True, 'status': dep_status})}\n\n"

        return StreamingResponse(
            _finished_stream(),
            media_type="text/event-stream",
            headers=sse_headers,
        )

    # Deployment is in progress — subscribe to live stream.
    result = broadcaster.subscribe(dep_id)
    if result is None:
        raise HTTPException(404, "No live stream available for this deployment")

    existing_lines, queue = result

    async def _live_stream() -> AsyncIterator[str]:
        try:
            for line in existing_lines:
                yield f"data: {json.dumps({'line': line})}\n\n"
            while True:
                item = await queue.get()
                if item is None:
                    with get_session() as session:
                        dep = session.query(Deployment).filter(Deployment.id == dep_id).first()
                        status = dep.status if dep else "unknown"
                    yield f"data: {json.dumps({'done': True, 'status': status})}\n\n"
                    break
                yield f"data: {json.dumps({'line': item})}\n\n"
        finally:
            broadcaster.unsubscribe(dep_id, queue)

    return StreamingResponse(
        _live_stream(),
        media_type="text/event-stream",
        headers=sse_headers,
    )


@router.get("/{name}/health", response_model=AppHealth)
def app_health(name: str, server: str | None = None) -> AppHealth:
    """Check real container health state and reconcile DB status."""
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name)
        if server:
            q = q.join(Server).filter(Server.name == server)
        app_obj = q.first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        db_status = app_obj.status
        app_id = app_obj.id
        health_check_url = app_obj.health_check_url
        app_port = app_obj.port
        ssh = _ssh_for(app_obj.server)

    http_result = None
    try:
        with ssh:
            raw_containers = get_container_health(ssh, name)
            actual_status = reconcile_app_status(ssh, name)
            if health_check_url:
                from cli.core.health import check_app_health

                http_result = check_app_health(ssh, app_port, health_check_url)
    except SSHConnectionError as exc:
        raise HTTPException(502, f"Cannot reach server: {exc}")

    if actual_status != db_status:
        with get_session() as session:
            a = session.query(App).filter(App.id == app_id).first()
            if a:
                a.status = actual_status

    containers = [
        ContainerHealth(
            name=c["name"],
            state=c["state"],
            status=c["status"],
            image=c["image"],
            health=c["health"],
        )
        for c in raw_containers
    ]

    http_health = None
    if http_result:
        http_health = AppHealthCheckResult(**http_result)

    return AppHealth(
        app_name=name,
        db_status=db_status,
        actual_status=actual_status,
        status_mismatch=(actual_status != db_status),
        containers=containers,
        http_health=http_health,
        checked_at=datetime.utcnow(),
    )


@router.post("/{name}/restart")
def restart(name: str, server: str | None = None) -> dict[str, str]:
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name)
        if server:
            q = q.join(Server).filter(Server.name == server)
        app_obj = q.first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        ssh = _ssh_for(app_obj.server)

    with ssh:
        restart_app(ssh, name)
    return {"message": f"App '{name}' restarted"}


@router.post("/{name}/stop")
def stop(name: str, server: str | None = None) -> dict[str, str]:
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name)
        if server:
            q = q.join(Server).filter(Server.name == server)
        app_obj = q.first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        ssh = _ssh_for(app_obj.server)
        app_id = app_obj.id

    with ssh:
        stop_app(ssh, name)

    with get_session() as session:
        a = session.query(App).filter(App.id == app_id).first()
        if a:
            a.status = "stopped"

    return {"message": f"App '{name}' stopped"}


@router.delete("/{name}")
def destroy(name: str, server: str | None = None) -> dict[str, str]:
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name)
        if server:
            q = q.join(Server).filter(Server.name == server)
        app_obj = q.first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        ssh = _ssh_for(app_obj.server)
        app_id = app_obj.id
        app_domain = app_obj.domain

    with ssh:
        destroy_app(ssh, name)
        if app_domain:
            remove_domain(ssh, app_domain)

    with get_session() as session:
        a = session.query(App).filter(App.id == app_id).first()
        if a:
            session.delete(a)

    return {"message": f"App '{name}' destroyed"}


# ── Scale ─────────────────────────────────────────────────────────────────────


@router.post("/{name}/scale")
def scale_app(name: str, body: ScaleInput) -> dict[str, str | int]:
    """Scale an app to N replicas."""
    init_db()
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == name).first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        app_obj.replicas = body.replicas
    return {"message": f"Scaled '{name}' to {body.replicas} replica(s)", "replicas": body.replicas}


# ── Single Deployment ─────────────────────────────────────────────────────────


@router.get("/{name}/deployments/{dep_id}", response_model=DeploymentOut)
def get_deployment(name: str, dep_id: int) -> DeploymentOut:
    """Get a single deployment with full log."""
    init_db()
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == name).first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        dep = (
            session.query(Deployment)
            .filter(Deployment.id == dep_id, Deployment.app_id == app_obj.id)
            .first()
        )
        if not dep:
            raise HTTPException(404, f"Deployment {dep_id} not found")
        return DeploymentOut.model_validate(dep)


# ── Dependencies ──────────────────────────────────────────────────────────────


@router.get("/{name}/dependencies", response_model=list[AppDependencyOut])
def list_dependencies(name: str) -> list[AppDependencyOut]:
    """List dependencies of an app."""
    init_db()
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == name).first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        deps = session.query(AppDependency).filter(AppDependency.app_id == app_obj.id).all()
        result = []
        for d in deps:
            dep_app = session.query(App).filter(App.id == d.depends_on_app_id).first()
            if dep_app:
                result.append(
                    AppDependencyOut(
                        id=d.id,
                        app_name=app_obj.name,
                        depends_on_app_name=dep_app.name,
                    )
                )
        return result


@router.post("/{name}/dependencies")
def add_dependency(name: str, body: AppDependencyCreate) -> dict[str, str]:
    """Add a dependency to an app."""
    init_db()
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == name).first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        dep_app = session.query(App).filter(App.name == body.depends_on).first()
        if not dep_app:
            raise HTTPException(404, f"App '{body.depends_on}' not found")
        if app_obj.id == dep_app.id:
            raise HTTPException(400, "An app cannot depend on itself")

        # Cycle detection
        if _would_create_cycle_api(session, app_obj.id, dep_app.id):
            raise HTTPException(400, "Adding this dependency would create a cycle")

        existing = (
            session.query(AppDependency)
            .filter(
                AppDependency.app_id == app_obj.id,
                AppDependency.depends_on_app_id == dep_app.id,
            )
            .first()
        )
        if existing:
            raise HTTPException(400, f"'{name}' already depends on '{body.depends_on}'")
        session.add(AppDependency(app_id=app_obj.id, depends_on_app_id=dep_app.id))
    return {"message": f"'{name}' now depends on '{body.depends_on}'"}


@router.delete("/{name}/dependencies/{dep_name}")
def remove_dependency(name: str, dep_name: str) -> dict[str, str]:
    """Remove a dependency from an app."""
    init_db()
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == name).first()
        if not app_obj:
            raise HTTPException(404, f"App '{name}' not found")
        dep_app = session.query(App).filter(App.name == dep_name).first()
        if not dep_app:
            raise HTTPException(404, f"App '{dep_name}' not found")
        dep = (
            session.query(AppDependency)
            .filter(
                AppDependency.app_id == app_obj.id,
                AppDependency.depends_on_app_id == dep_app.id,
            )
            .first()
        )
        if not dep:
            raise HTTPException(404, f"'{name}' does not depend on '{dep_name}'")
        session.delete(dep)
    return {"message": f"Removed dependency: '{name}' no longer depends on '{dep_name}'"}


def _would_create_cycle_api(session: object, app_id: int, depends_on_id: int) -> bool:
    """Return True if adding app_id -> depends_on_id creates a cycle."""
    visited: set[int] = set()
    stack = [depends_on_id]
    while stack:
        current = stack.pop()
        if current == app_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        deps = (
            session.query(AppDependency)  # type: ignore[attr-defined]
            .filter(AppDependency.app_id == current)
            .all()
        )
        stack.extend(d.depends_on_app_id for d in deps)
    return False
