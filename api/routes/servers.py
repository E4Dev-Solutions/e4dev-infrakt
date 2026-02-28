"""Server management API routes."""

import asyncio
import json
import logging
import threading
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import selectinload

from api.log_broadcaster import broadcaster
from api.schemas import (
    DiskUsage,
    MemoryUsage,
    ServerContainerInfo,
    ServerCreate,
    ServerMetricOut,
    ServerOut,
    ServerStatus,
    ServerTagCreate,
    ServerUpdate,
)
from cli.core.database import get_session, init_db
from cli.core.exceptions import SSHConnectionError
from cli.core.provisioner import provision_server, wipe_server
from cli.core.ssh import SSHClient
from cli.models.server import Server
from cli.models.server_metric import ServerMetric
from cli.models.server_tag import ServerTag

router = APIRouter(prefix="/servers", tags=["servers"])
logger = logging.getLogger(__name__)


def _ssh_for(srv: Server) -> SSHClient:
    return SSHClient.from_server(srv)


@router.get("", response_model=list[ServerOut])
def list_servers(tag: str | None = None) -> list[ServerOut]:
    """List all registered servers, optionally filtered by tag."""
    init_db()
    with get_session() as session:
        q = (
            session.query(Server)
            .options(selectinload(Server.apps), selectinload(Server.tags))
            .order_by(Server.name)
        )
        if tag:
            q = q.join(ServerTag).filter(ServerTag.tag == tag)
        servers = q.all()
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
                tags=[t.tag for t in s.tags],
                is_infrakt_host=s.is_infrakt_host,
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
            tags=[],
            is_infrakt_host=srv.is_infrakt_host,
        )


@router.put("/{name}", response_model=ServerOut)
def update_server(name: str, body: ServerUpdate) -> ServerOut:
    """Update a server's connection details."""
    init_db()
    with get_session() as session:
        srv = (
            session.query(Server)
            .options(selectinload(Server.apps), selectinload(Server.tags))
            .filter(Server.name == name)
            .first()
        )
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")

        if body.host is not None:
            srv.host = body.host
        if body.user is not None:
            srv.user = body.user
        if body.port is not None:
            srv.port = body.port
        if body.ssh_key_path is not None:
            srv.ssh_key_path = body.ssh_key_path
        if body.provider is not None:
            srv.provider = body.provider
        if body.is_infrakt_host is not None:
            srv.is_infrakt_host = body.is_infrakt_host

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
            app_count=len(srv.apps),
            tags=[t.tag for t in srv.tags],
            is_infrakt_host=srv.is_infrakt_host,
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
async def provision(name: str, background_tasks: BackgroundTasks) -> dict[str, str | int]:
    """Start provisioning a server in the background."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")
        srv.status = "provisioning"
        srv_id = srv.id
        is_infrakt_host = srv.is_infrakt_host
        host, user, port, key_path = srv.host, srv.user, srv.port, srv.ssh_key_path

    # Use negative server ID to avoid collision with deployment IDs
    prov_key = -srv_id
    loop = asyncio.get_running_loop()
    broadcaster.register(prov_key, loop)

    def _do_provision() -> None:
        try:
            ssh = SSHClient(host=host, user=user, port=port, key_path=key_path)
            with ssh:
                # Wipe non-infrakT-host servers first
                if not is_infrakt_host:

                    def _on_wipe_step(step_name: str, index: int, total: int) -> None:
                        broadcaster.publish(prov_key, f"[wipe {index + 1}/{total}] {step_name}")

                    wipe_server(ssh, on_step=_on_wipe_step)

                    # Clean local app records
                    with get_session() as session:
                        s = session.query(Server).filter(Server.name == name).first()
                        if s:
                            for app in s.apps:
                                session.delete(app)

                # Wipe non-infrakT-host servers first
                if not is_infrakt_host:

                    def _on_wipe_step(step_name: str, index: int, total: int) -> None:
                        broadcaster.publish(prov_key, f"[wipe {index + 1}/{total}] {step_name}")

                    wipe_server(ssh, on_step=_on_wipe_step)

                    # Clean local app records
                    with get_session() as session:
                        s = session.query(Server).filter(Server.name == name).first()
                        if s:
                            for app in s.apps:
                                session.delete(app)

                def _on_step(step_name: str, index: int, total: int) -> None:
                    broadcaster.publish(prov_key, f"[{index + 1}/{total}] {step_name}")

                provision_server(ssh, on_step=_on_step)

            broadcaster.publish(prov_key, "Provisioning complete")
            with get_session() as session:
                s = session.query(Server).filter(Server.name == name).first()
                if s:
                    s.status = "active"
        except SSHConnectionError as exc:
            logger.error("Provisioning failed for %s: %s", name, exc)
            broadcaster.publish(prov_key, f"Error: {exc}")
            with get_session() as session:
                s = session.query(Server).filter(Server.name == name).first()
                if s:
                    s.status = "inactive"
        except Exception as exc:
            logger.exception("Unexpected error provisioning %s", name)
            broadcaster.publish(prov_key, f"Error: {exc}")
            with get_session() as session:
                s = session.query(Server).filter(Server.name == name).first()
                if s:
                    s.status = "inactive"
        finally:
            broadcaster.finish(prov_key)
            threading.Timer(300, broadcaster.cleanup, args=[prov_key]).start()

    background_tasks.add_task(_do_provision)
    return {
        "message": f"Provisioning started for '{name}'",
        "provision_key": prov_key,
    }


@router.get("/{name}/provision/stream")
async def stream_provision_logs(name: str, key: int) -> StreamingResponse:
    """Stream provisioning progress via Server-Sent Events."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")
        srv_status = srv.status

    sse_headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no",
    }

    # If provisioning already finished and no broadcaster entry, send done
    if srv_status in ("active", "inactive") and not broadcaster.has(key):

        async def _finished() -> AsyncIterator[str]:
            yield (f"data: {json.dumps({'done': True, 'status': srv_status})}\n\n")

        return StreamingResponse(_finished(), media_type="text/event-stream", headers=sse_headers)

    # Subscribe to live stream
    result = broadcaster.subscribe(key)
    if result is None:

        async def _no_stream() -> AsyncIterator[str]:
            yield f"data: {json.dumps({'done': True, 'status': srv_status})}\n\n"

        return StreamingResponse(_no_stream(), media_type="text/event-stream", headers=sse_headers)
    existing, queue = result

    async def _stream() -> AsyncIterator[str]:
        for line in existing:
            yield f"data: {json.dumps({'line': line})}\n\n"
        while True:
            line = await queue.get()
            if line is None:
                break
            yield f"data: {json.dumps({'line': line})}\n\n"
        # Fetch final status
        with get_session() as session:
            s = session.query(Server).filter(Server.name == name).first()
            final = s.status if s else "inactive"
        yield f"data: {json.dumps({'done': True, 'status': final})}\n\n"

    return StreamingResponse(_stream(), media_type="text/event-stream", headers=sse_headers)


def _fmt_bytes(n: int) -> str:
    """Format bytes as a human-readable string."""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024:
            return f"{n:.1f} {unit}"
        n = n // 1024
    return f"{n:.1f} PB"


def _parse_memory(raw: str) -> MemoryUsage | None:
    """Parse output of: free -b | awk '/^Mem:/{print $2, $3, $4}'."""
    parts = raw.split()
    if len(parts) < 3:
        return None
    try:
        total, used, free = int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError:
        return None
    percent = round((used / total) * 100, 1) if total > 0 else 0.0
    return MemoryUsage(
        total=_fmt_bytes(total), used=_fmt_bytes(used), free=_fmt_bytes(free), percent=percent
    )


def _parse_disk(raw: str) -> DiskUsage | None:
    """Parse output of: df -B1 / | awk 'NR==2{print $2, $3, $4, $5}'."""
    parts = raw.split()
    if len(parts) < 4:
        return None
    try:
        total, used, avail = int(parts[0]), int(parts[1]), int(parts[2])
        percent = float(parts[3].rstrip("%"))
    except ValueError:
        return None
    return DiskUsage(
        total=_fmt_bytes(total), used=_fmt_bytes(used), free=_fmt_bytes(avail), percent=percent
    )


def _parse_cpu(raw: str) -> float | None:
    """Parse CPU usage percentage from top output."""
    try:
        return round(float(raw.strip()), 1)
    except (ValueError, AttributeError):
        return None


def _parse_containers(raw: str) -> list[ServerContainerInfo]:
    """Parse docker ps --format JSON output into ServerContainerInfo list."""
    results: list[ServerContainerInfo] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            results.append(
                ServerContainerInfo(
                    id=obj.get("ID", ""),
                    name=obj.get("Names", ""),
                    status=obj.get("Status", ""),
                    image=obj.get("Image", ""),
                )
            )
        except json.JSONDecodeError:
            continue
    return results


@router.get("/{name}/status", response_model=ServerStatus)
def server_status(name: str) -> ServerStatus:
    """Show server resource usage and Docker status."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")
        ssh = _ssh_for(srv)
        srv_id = srv.id
        srv_name = srv.name
        srv_host = srv.host

    try:
        with ssh:
            uptime = ssh.run_checked("uptime -p").strip()
            mem_raw, _, _ = ssh.run("free -b | awk '/^Mem:/{print $2, $3, $4}'", timeout=10)
            disk_raw, _, _ = ssh.run("df -B1 / | awk 'NR==2{print $2, $3, $4, $5}'", timeout=10)
            cpu_raw, _, _ = ssh.run("top -bn1 | grep 'Cpu(s)' | awk '{print $2+$4}'", timeout=10)
            containers_raw, _, _ = ssh.run(
                'docker ps --format \'{"ID":"{{.ID}}","Names":"{{.Names}}",'
                '"Status":"{{.Status}}","Image":"{{.Image}}"}\' 2>/dev/null',
                timeout=10,
            )
    except SSHConnectionError as exc:
        raise HTTPException(502, f"Cannot reach server: {exc}")

    memory = _parse_memory(mem_raw.strip())
    disk = _parse_disk(disk_raw.strip())
    cpu_pct = _parse_cpu(cpu_raw.strip())

    # Persist metric snapshot
    with get_session() as session:
        session.add(
            ServerMetric(
                server_id=srv_id,
                cpu_percent=cpu_pct,
                mem_percent=memory.percent if memory else None,
                disk_percent=disk.percent if disk else None,
            )
        )
        # Clean up metrics older than 30 days
        cutoff = datetime.now(UTC) - timedelta(days=30)
        session.query(ServerMetric).filter(
            ServerMetric.server_id == srv_id,
            ServerMetric.recorded_at < cutoff,
        ).delete()

    return ServerStatus(
        name=srv_name,
        host=srv_host,
        uptime=uptime,
        memory=memory,
        disk=disk,
        cpu=cpu_pct,
        containers=_parse_containers(containers_raw.strip()),
    )


@router.get("/{name}/metrics", response_model=list[ServerMetricOut])
def server_metrics(name: str, hours: int = 24) -> list[ServerMetricOut]:
    """Return time-series metric snapshots for a server."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")
        cutoff = datetime.now(UTC) - timedelta(hours=hours)
        metrics = (
            session.query(ServerMetric)
            .filter(
                ServerMetric.server_id == srv.id,
                ServerMetric.recorded_at >= cutoff,
            )
            .order_by(ServerMetric.recorded_at.asc())
            .all()
        )
        return [ServerMetricOut.model_validate(m) for m in metrics]


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


# ── Tags ──────────────────────────────────────────────────────────────────────


@router.get("/{name}/tags")
def list_tags(name: str) -> list[str]:
    """List tags for a server."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")
        tags = session.query(ServerTag).filter(ServerTag.server_id == srv.id).all()
        return [t.tag for t in tags]


@router.post("/{name}/tags")
def add_tag(name: str, body: ServerTagCreate) -> dict[str, str]:
    """Add a tag to a server."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")
        existing = (
            session.query(ServerTag)
            .filter(ServerTag.server_id == srv.id, ServerTag.tag == body.tag)
            .first()
        )
        if existing:
            raise HTTPException(400, f"Tag '{body.tag}' already exists on '{name}'")
        session.add(ServerTag(server_id=srv.id, tag=body.tag))
    return {"message": f"Tag '{body.tag}' added to '{name}'"}


@router.delete("/{name}/tags/{tag}")
def remove_tag(name: str, tag: str) -> dict[str, str]:
    """Remove a tag from a server."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise HTTPException(404, f"Server '{name}' not found")
        existing = (
            session.query(ServerTag)
            .filter(ServerTag.server_id == srv.id, ServerTag.tag == tag)
            .first()
        )
        if not existing:
            raise HTTPException(404, f"Tag '{tag}' not found on '{name}'")
        session.delete(existing)
    return {"message": f"Tag '{tag}' removed from '{name}'"}
