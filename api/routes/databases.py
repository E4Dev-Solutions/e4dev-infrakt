"""Database service management API routes."""

import logging
import secrets
import shlex

from fastapi import APIRouter, BackgroundTasks, HTTPException

from api.schemas import (
    BackupFileOut,
    BackupScheduleCreate,
    DatabaseCreate,
    DatabaseOut,
    DatabaseRestore,
    DatabaseStats,
)
from cli.commands.db import DB_TEMPLATES, DEFAULT_VERSIONS, _generate_db_compose
from cli.core.backup import (
    backup_database,
    install_backup_cron,
    list_backups,
    remove_backup_cron,
    restore_database,
)
from cli.core.database import get_session, init_db
from cli.core.db_stats import get_database_stats
from cli.core.deployer import _validate_name
from cli.core.exceptions import SSHConnectionError
from cli.core.ssh import SSHClient
from cli.core.webhook_sender import fire_webhooks
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
        return [_get_db_out(d) for d in dbs]


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

        existing = session.query(App).filter(App.name == body.name, App.server_id == srv.id).first()
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


def _get_db_out(db_app: App) -> DatabaseOut:
    """Build a DatabaseOut from an App record."""
    parent_name: str | None = None
    if db_app.parent_app_id and db_app.parent_app:
        parent_name = db_app.parent_app.name
    return DatabaseOut(
        id=db_app.id,
        name=db_app.name,
        server_name=db_app.server.name,
        db_type=db_app.app_type.split(":", 1)[1],
        port=db_app.port,
        status=db_app.status,
        backup_schedule=db_app.backup_schedule,
        parent_app_name=parent_name,
        created_at=db_app.created_at,
        updated_at=db_app.updated_at,
    )


@router.get("/{name}/backups", response_model=list[BackupFileOut])
def list_database_backups(name: str, server: str | None = None) -> list[BackupFileOut]:
    """List backup files for a database on the remote server."""
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name, App.app_type.like("db:%"))
        if server:
            q = q.join(Server).filter(Server.name == server)
        db_app = q.first()
        if not db_app:
            raise HTTPException(404, f"Database '{name}' not found")
        srv = db_app.server
        ssh = SSHClient.from_server(srv)

    try:
        with ssh:
            backups = list_backups(ssh, db_app)
    except (SSHConnectionError, Exception):
        return []

    return [BackupFileOut(**b) for b in backups]


@router.get("/{name}", response_model=DatabaseOut)
def get_database(name: str, server: str | None = None) -> DatabaseOut:
    """Get details for a single database."""
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name, App.app_type.like("db:%"))
        if server:
            q = q.join(Server).filter(Server.name == server)
        db_app = q.first()
        if not db_app:
            raise HTTPException(404, f"Database '{name}' not found")
        return _get_db_out(db_app)


@router.get("/{name}/stats", response_model=DatabaseStats)
def database_stats(name: str, server: str | None = None) -> DatabaseStats:
    """Get live database statistics."""
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name, App.app_type.like("db:%"))
        if server:
            q = q.join(Server).filter(Server.name == server)
        db_app = q.first()
        if not db_app:
            raise HTTPException(404, f"Database '{name}' not found")
        db_type = db_app.app_type.split(":", 1)[1]
        ssh = SSHClient.from_server(db_app.server)

    try:
        with ssh:
            stats = get_database_stats(ssh, name, db_type)
    except Exception as exc:
        raise HTTPException(502, f"Cannot reach server: {exc}")

    return DatabaseStats(**stats)


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


@router.post("/{name}/backup")
def backup_database_endpoint(name: str, server: str | None = None) -> dict[str, str]:
    """Trigger a database backup on the remote server."""
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name, App.app_type.like("db:%"))
        if server:
            q = q.join(Server).filter(Server.name == server)
        db_app = q.first()
        if not db_app:
            raise HTTPException(404, f"Database '{name}' not found")
        srv = db_app.server
        ssh = SSHClient.from_server(srv)

    with ssh:
        remote_path = backup_database(ssh, db_app)

    filename = remote_path.rsplit("/", 1)[-1]
    fire_webhooks("backup.complete", {"database": name, "filename": filename})
    return {
        "message": f"Backup created: {filename}",
        "filename": filename,
        "remote_path": remote_path,
    }


@router.post("/{name}/restore")
def restore_database_endpoint(name: str, body: DatabaseRestore) -> dict[str, str]:
    """Restore a database from a backup file on the server."""
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name, App.app_type.like("db:%"))
        if body.server_name:
            q = q.join(Server).filter(Server.name == body.server_name)
        db_app = q.first()
        if not db_app:
            raise HTTPException(404, f"Database '{name}' not found")
        srv = db_app.server
        ssh = SSHClient.from_server(srv)

    remote_path = f"/opt/infrakt/backups/{body.filename}"
    try:
        with ssh:
            restore_database(ssh, db_app, remote_path)
    except SSHConnectionError as exc:
        if "not found" in str(exc):
            raise HTTPException(404, f"Backup file not found: {body.filename}")
        raise HTTPException(500, str(exc))

    fire_webhooks("backup.restore", {"database": name, "filename": body.filename})
    return {"message": f"Database '{name}' restored from {body.filename}"}


@router.post("/{name}/schedule")
def schedule_backup_endpoint(
    name: str, body: BackupScheduleCreate, server: str | None = None
) -> dict[str, str]:
    """Schedule automatic backups for a database via cron."""
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name, App.app_type.like("db:%"))
        if server:
            q = q.join(Server).filter(Server.name == server)
        db_app = q.first()
        if not db_app:
            raise HTTPException(404, f"Database '{name}' not found")
        srv = db_app.server
        ssh = SSHClient.from_server(srv)
        app_id = db_app.id

    with ssh:
        install_backup_cron(ssh, db_app, body.cron_expression, body.retention_days)

    with get_session() as session:
        a = session.query(App).filter(App.id == app_id).first()
        if a:
            a.backup_schedule = body.cron_expression

    return {
        "message": f"Scheduled backups for '{name}' with cron '{body.cron_expression}'",
        "cron_expression": body.cron_expression,
        "retention_days": str(body.retention_days),
    }


@router.delete("/{name}/schedule")
def unschedule_backup_endpoint(name: str, server: str | None = None) -> dict[str, str]:
    """Remove scheduled backups for a database."""
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.name == name, App.app_type.like("db:%"))
        if server:
            q = q.join(Server).filter(Server.name == server)
        db_app = q.first()
        if not db_app:
            raise HTTPException(404, f"Database '{name}' not found")
        srv = db_app.server
        ssh = SSHClient.from_server(srv)
        app_id = db_app.id

    with ssh:
        remove_backup_cron(ssh, db_app)

    with get_session() as session:
        a = session.query(App).filter(App.id == app_id).first()
        if a:
            a.backup_schedule = None

    return {"message": f"Removed scheduled backups for '{name}'"}
