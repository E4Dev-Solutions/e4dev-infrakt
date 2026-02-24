"""Database service management API routes."""

import logging
import secrets
import shlex

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.schemas import DatabaseCreate, DatabaseOut
from cli.commands.db import DB_TEMPLATES, DEFAULT_VERSIONS, _generate_db_compose
from cli.core.database import get_session, init_db
from cli.core.deployer import _validate_name
from cli.core.ssh import SSHClient
from cli.models.app import App
from cli.models.server import Server

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/databases", tags=["databases"])


@router.get("", response_model=list[DatabaseOut])
def list_databases(server: str | None = None) -> list[DatabaseOut]:
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.app_type.like("db:%")).join(Server)
        if server:
            q = q.filter(Server.name == server)
        dbs = q.order_by(App.name).all()
        return [
            DatabaseOut(
                id=d.id,
                name=d.name,
                server_name=d.server.name,
                db_type=d.app_type.split(":", 1)[1],
                port=d.port,
                status=d.status,
            )
            for d in dbs
        ]


@router.post("", status_code=201)
def create_database(body: DatabaseCreate, background_tasks: BackgroundTasks) -> dict[str, str]:
    init_db()
    if body.db_type not in DB_TEMPLATES:
        supported = list(DB_TEMPLATES.keys())
        raise HTTPException(
            400,
            f"Unsupported type: {body.db_type}. Use: {supported}",
        )

    version = body.version or DEFAULT_VERSIONS.get(body.db_type, "latest")
    password = secrets.token_urlsafe(24)

    with get_session() as session:
        srv = session.query(Server).filter(Server.name == body.server_name).first()
        if not srv:
            raise HTTPException(404, f"Server '{body.server_name}' not found")

        existing = (
            session.query(App)
            .filter(App.name == body.name, App.server_id == srv.id)
            .first()
        )
        if existing:
            raise HTTPException(
                400,
                f"Service '{body.name}' already exists on '{body.server_name}'",
            )

        db_app = App(
            name=body.name,
            server_id=srv.id,
            port=DB_TEMPLATES[body.db_type]["port"],
            app_type=f"db:{body.db_type}",
            status="deploying",
        )
        session.add(db_app)
        session.flush()
        app_id = db_app.id
        ssh_data = {
            "host": srv.host,
            "user": srv.user,
            "port": srv.port,
            "key_path": srv.ssh_key_path,
        }

    _validate_name(body.name, "database name")
    compose = _generate_db_compose(body.db_type, body.name, version, password)
    app_path = f"/opt/infrakt/apps/{body.name}"
    q_path = shlex.quote(app_path)

    def _do_create() -> None:
        try:
            host = ssh_data.get("host")
            user = ssh_data.get("user")
            port = ssh_data.get("port")
            key_path = ssh_data.get("key_path")
            port_int: int = 22
            if isinstance(port, int):
                port_int = port
            elif port is not None:
                port_int = int(str(port))
            ssh = SSHClient(
                host=str(host or ""),
                user=str(user or "root"),
                port=port_int,
                key_path=key_path if isinstance(key_path, (str, type(None))) else None,
            )
            with ssh:
                ssh.run("docker network create infrakt 2>/dev/null || true")
                ssh.run_checked(f"mkdir -p {q_path}")
                ssh.upload_string(compose, f"{app_path}/docker-compose.yml")
                ssh.run_checked(f"cd {q_path} && docker compose up -d", timeout=120)
            with get_session() as session:
                a = session.query(App).filter(App.id == app_id).first()
                if a:
                    a.status = "running"
        except Exception:
            logger.exception("Failed to create database %s", body.name)
            with get_session() as session:
                a = session.query(App).filter(App.id == app_id).first()
                if a:
                    a.status = "error"

    background_tasks.add_task(_do_create)
    return {"message": f"Creating {body.db_type} database '{body.name}'", "password": password}


@router.delete("/{name}")
def destroy_database(name: str, server: str | None = None) -> dict[str, str]:
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name, App.app_type.like("db:%"))
        if server:
            q = q.join(Server).filter(Server.name == server)
        app_obj = q.first()
        if not app_obj:
            raise HTTPException(404, f"Database '{name}' not found")
        srv = app_obj.server
        ssh = SSHClient.from_server(srv)
        app_id = app_obj.id

    try:
        _validate_name(name, "database name")
    except Exception:
        raise HTTPException(400, f"Invalid database name: {name!r}")
    app_path = f"/opt/infrakt/apps/{name}"
    q_path = shlex.quote(app_path)
    with ssh:
        ssh.run(f"cd {q_path} && docker compose down -v --remove-orphans", timeout=60)
        ssh.run_checked(f"rm -rf {q_path}")

    with get_session() as session:
        a = session.query(App).filter(App.id == app_id).first()
        if a:
            session.delete(a)

    return {"message": f"Database '{name}' destroyed"}
