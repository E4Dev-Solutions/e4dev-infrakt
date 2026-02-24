"""Server management API routes."""

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException
from sqlalchemy.orm import selectinload

from api.schemas import ServerCreate, ServerOut, ServerStatus
from cli.core.database import get_session, init_db
from cli.core.exceptions import SSHConnectionError
from cli.core.provisioner import provision_server
from cli.core.ssh import SSHClient
from cli.models.server import Server

router = APIRouter(prefix="/servers", tags=["servers"])
logger = logging.getLogger(__name__)


def _ssh_for(srv: Server) -> SSHClient:
    return SSHClient.from_server(srv)


@router.get("", response_model=list[ServerOut])
def list_servers() -> list[ServerOut]:
    """List all registered servers."""
    init_db()
    with get_session() as session:
        servers = (
            session.query(Server)
            .options(selectinload(Server.apps))
            .order_by(Server.name)
            .all()
        )
        return [
            ServerOut(
                id=s.id,
                name=s.name,
                host=s.host,
                user=s.user,
                port=s.port,
                ssh_key_path=s.ssh_key_path,
                status=s.status,
                provider=s.provider,
                created_at=s.created_at,
                updated_at=s.updated_at,
                app_count=len(s.apps),
            )
            for s in servers
        ]


@router.post("", response_model=ServerOut, status_code=201)
def add_server(body: ServerCreate) -> ServerOut:
    """Register a new server."""
    init_db()
    with get_session() as session:
        existing = session.query(Server).filter(Server.name == body.name).first()
        if existing:
            raise HTTPException(400, f"Server '{body.name}' already exists")

        srv = Server(
            name=body.name,
            host=body.host,
            user=body.user,
            port=body.port,
            ssh_key_path=body.ssh_key_path,
            provider=body.provider,
            status="inactive",
        )
        session.add(srv)
        session.flush()

        return ServerOut(
            id=srv.id,
            name=srv.name,
            host=srv.host,
            user=srv.user,
            port=srv.port,
            ssh_key_path=srv.ssh_key_path,
            status=srv.status,
            provider=srv.provider,
            created_at=srv.created_at,
            updated_at=srv.updated_at,
            app_count=0,
        )


@router.delete("/{name}")
def remove_server(name: str) -> dict[str, str]:
    """Remove a registered server."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")
        session.delete(srv)
    return {"message": f"Server '{name}' removed"}


@router.post("/{name}/provision")
def provision(name: str, background_tasks: BackgroundTasks) -> dict[str, str]:
    """Start provisioning a server in the background."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")
        srv.status = "provisioning"
        host, user, port, key_path = srv.host, srv.user, srv.port, srv.ssh_key_path

    def _do_provision() -> None:
        try:
            ssh = SSHClient(host=host, user=user, port=port, key_path=key_path)
            with ssh:
                provision_server(ssh)
            with get_session() as session:
                s = session.query(Server).filter(Server.name == name).first()
                if s:
                    s.status = "active"
        except SSHConnectionError as exc:
            logger.error("Provisioning failed for %s: %s", name, exc)
            with get_session() as session:
                s = session.query(Server).filter(Server.name == name).first()
                if s:
                    s.status = "inactive"
        except Exception as exc:
            logger.exception("Unexpected error provisioning %s", name)
            with get_session() as session:
                s = session.query(Server).filter(Server.name == name).first()
                if s:
                    s.status = "inactive"

    background_tasks.add_task(_do_provision)
    return {"message": f"Provisioning started for '{name}'"}


@router.get("/{name}/status", response_model=ServerStatus)
def server_status(name: str) -> ServerStatus:
    """Show server resource usage and Docker status."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")
        ssh = _ssh_for(srv)
        srv_name = srv.name
        srv_host = srv.host

    try:
        with ssh:
            uptime = ssh.run_checked("uptime -p").strip()
            mem = ssh.run_checked("free -h | awk '/Mem:/{print $3\"/\"$2}'").strip()
            disk = ssh.run_checked("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\" used)\"}'").strip()
            containers = ssh.run_checked(
                "docker ps --format '{{.Names}}\\t{{.Status}}' 2>/dev/null || echo 'Docker not running'"
            ).strip()
    except SSHConnectionError as exc:
        raise HTTPException(502, f"Cannot reach server: {exc}")

    return ServerStatus(
        name=srv_name,
        host=srv_host,
        uptime=uptime,
        memory=mem,
        disk=disk,
        containers=containers,
    )


@router.post("/{name}/test")
def test_connection(name: str) -> dict[str, bool]:
    """Test SSH connectivity to a server."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")
        ssh = _ssh_for(srv)

    ok = ssh.test_connection()
    return {"reachable": ok}
