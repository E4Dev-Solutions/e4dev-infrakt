"""App management API routes."""

import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy.orm import joinedload

from api.schemas import AppCreate, AppLogs, AppOut, DeploymentOut
from cli.core.crypto import env_content_for_app
from cli.core.database import get_session, init_db
from cli.core.deployer import deploy_app, destroy_app, get_logs, restart_app, stop_app
from cli.core.exceptions import SSHConnectionError
from cli.core.proxy_manager import add_domain, remove_domain
from cli.core.ssh import SSHClient
from cli.models.app import App
from cli.models.deployment import Deployment
from cli.models.server import Server

router = APIRouter(prefix="/apps", tags=["apps"])
logger = logging.getLogger(__name__)


def _ssh_for(srv: Server) -> SSHClient:
    return SSHClient.from_server(srv)


@router.get("", response_model=list[AppOut])
def list_apps(server: str | None = None) -> list[AppOut]:
    """List all apps, optionally filtered by server."""
    init_db()
    with get_session() as session:
        q = session.query(App).join(Server).options(joinedload(App.server))
        if server:
            q = q.filter(Server.name == server)
        apps = q.filter(~App.app_type.like("db:%")).order_by(Server.name, App.name).all()
        return [
            AppOut(
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
                created_at=a.created_at,
                updated_at=a.updated_at,
            )
            for a in apps
        ]


@router.post("", response_model=AppOut, status_code=201)
def create_app(body: AppCreate):
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
        )
        session.add(new_app)
        session.flush()

        return AppOut(
            id=new_app.id,
            name=new_app.name,
            server_id=new_app.server_id,
            server_name=srv.name,
            domain=new_app.domain,
            port=new_app.port,
            git_repo=new_app.git_repo,
            branch=new_app.branch,
            image=new_app.image,
            status=new_app.status,
            app_type=new_app.app_type,
            created_at=new_app.created_at,
            updated_at=new_app.updated_at,
        )


@router.post("/{name}/deploy")
def deploy(name: str, server: str | None = None, background_tasks: BackgroundTasks = None):
    init_db()
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
        app_data = {
            "port": app_obj.port,
            "git_repo": app_obj.git_repo,
            "branch": app_obj.branch,
            "image": app_obj.image,
            "domain": app_obj.domain,
        }
        ssh_data = {
            "host": srv.host,
            "user": srv.user,
            "port": srv.port,
            "key_path": srv.ssh_key_path,
        }

    app_obj_status_update = {"id": app_id, "dep_id": dep_id}

    def _do_deploy():
        ssh = SSHClient(**ssh_data)
        try:
            with ssh:
                ssh.run("docker network create infrakt 2>/dev/null || true")
                env_content = env_content_for_app(app_id)
                log = deploy_app(
                    ssh,
                    name,
                    git_repo=app_data["git_repo"],
                    branch=app_data["branch"],
                    image=app_data["image"],
                    port=app_data["port"],
                    env_content=env_content,
                )
                if app_data["domain"]:
                    add_domain(ssh, app_data["domain"], app_data["port"])

            with get_session() as session:
                dep = session.query(Deployment).filter(Deployment.id == dep_id).first()
                if dep:
                    dep.status = "success"
                    dep.log = log
                    dep.finished_at = datetime.utcnow()
                a = session.query(App).filter(App.id == app_id).first()
                if a:
                    a.status = "running"
        except SSHConnectionError as exc:
            logger.error("Deployment SSH error for %s: %s", name, exc)
            with get_session() as session:
                dep = session.query(Deployment).filter(Deployment.id == dep_id).first()
                if dep:
                    dep.status = "failed"
                    dep.log = str(exc)
                    dep.finished_at = datetime.utcnow()
                a = session.query(App).filter(App.id == app_id).first()
                if a:
                    a.status = "error"
        except Exception as exc:
            logger.exception("Unexpected deployment error for %s", name)
            with get_session() as session:
                dep = session.query(Deployment).filter(Deployment.id == dep_id).first()
                if dep:
                    dep.status = "failed"
                    dep.log = str(exc)
                    dep.finished_at = datetime.utcnow()
                a = session.query(App).filter(App.id == app_id).first()
                if a:
                    a.status = "error"

    background_tasks.add_task(_do_deploy)
    return {"message": f"Deployment started for '{name}'", "deployment_id": dep_id}


@router.get("/{name}/logs", response_model=AppLogs)
def app_logs(name: str, server: str | None = None, lines: int = 100):
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


@router.get("/{name}/deployments", response_model=list[DeploymentOut])
def app_deployments(name: str):
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


@router.post("/{name}/restart")
def restart(name: str, server: str | None = None):
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
def stop(name: str, server: str | None = None):
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
def destroy(name: str, server: str | None = None):
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
