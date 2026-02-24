"""Proxy management API routes."""

from fastapi import APIRouter, HTTPException

from api.schemas import ProxyRoute, ProxyRouteCreate
from cli.core.database import get_session, init_db
from cli.core.exceptions import SSHConnectionError
from cli.core.proxy_manager import add_domain, get_status, list_domains, reload_proxy, remove_domain
from cli.core.ssh import SSHClient
from cli.models.server import Server

router = APIRouter(prefix="/proxy", tags=["proxy"])


def _get_ssh(server_name: str) -> SSHClient:
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            raise HTTPException(404, f"Server '{server_name}' not found")
        return SSHClient.from_server(srv)


@router.get("/{server_name}/domains", response_model=list[ProxyRoute])
def domains(server_name: str) -> list[ProxyRoute]:
    init_db()
    ssh = _get_ssh(server_name)
    try:
        with ssh:
            entries = list_domains(ssh)
    except SSHConnectionError as exc:
        raise HTTPException(502, str(exc))
    return [ProxyRoute(domain=d, port=p) for d, p in entries]


@router.post("/routes", status_code=201)
def add_route(body: ProxyRouteCreate) -> dict[str, str]:
    init_db()
    ssh = _get_ssh(body.server_name)
    try:
        with ssh:
            add_domain(ssh, body.domain, body.port)
    except SSHConnectionError as exc:
        raise HTTPException(502, str(exc))
    return {"message": f"Added {body.domain} -> localhost:{body.port}"}


@router.delete("/{server_name}/domains/{domain}")
def remove_route(server_name: str, domain: str) -> dict[str, str]:
    init_db()
    ssh = _get_ssh(server_name)
    try:
        with ssh:
            remove_domain(ssh, domain)
    except SSHConnectionError as exc:
        raise HTTPException(502, str(exc))
    return {"message": f"Removed {domain}"}


@router.get("/{server_name}/status")
def proxy_status(server_name: str) -> dict[str, str]:
    init_db()
    ssh = _get_ssh(server_name)
    try:
        with ssh:
            output = get_status(ssh)
    except SSHConnectionError as exc:
        raise HTTPException(502, str(exc))
    return {"status": output}


@router.post("/{server_name}/reload")
def reload(server_name: str) -> dict[str, str]:
    init_db()
    ssh = _get_ssh(server_name)
    try:
        with ssh:
            reload_proxy(ssh)
    except SSHConnectionError as exc:
        raise HTTPException(502, str(exc))
    return {"message": "Caddy reloaded"}
