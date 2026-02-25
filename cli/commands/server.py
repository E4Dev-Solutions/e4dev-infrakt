import click

from cli.core.console import error, info, print_table, status_spinner, success
from cli.core.database import get_session, init_db
from cli.core.exceptions import ServerNotFoundError
from cli.core.ssh import SSHClient
from cli.models.server import Server
from cli.models.server_tag import ServerTag


def _get_server(name: str) -> Server:
    """Look up a server by name or raise."""
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            raise ServerNotFoundError(f"Server '{name}' not found")
        # Detach from session so it's usable after close
        session.expunge(srv)
        return srv


def _ssh_for_server(srv: Server) -> SSHClient:
    return SSHClient.from_server(srv)


@click.group()
def server() -> None:
    """Manage remote servers."""


@server.command()
@click.option("--name", prompt="Server name", help="Unique name for this server")
@click.option("--host", prompt="Host (IP or hostname)", help="Server IP or hostname")
@click.option("--user", default="root", prompt="SSH user", help="SSH username")
@click.option("--port", default=22, help="SSH port")
@click.option("--key", "ssh_key_path", default=None, help="Path to SSH private key")
@click.option(
    "--provider",
    default=None,
    help="Cloud provider label (hetzner, digitalocean, etc.)",
)
def add(
    name: str,
    host: str,
    user: str,
    port: int,
    ssh_key_path: str | None,
    provider: str | None,
) -> None:
    """Register a new server."""
    init_db()
    with get_session() as session:
        existing = session.query(Server).filter(Server.name == name).first()
        if existing:
            error(f"Server '{name}' already exists")
            raise SystemExit(1)

        srv = Server(
            name=name,
            host=host,
            user=user,
            port=port,
            ssh_key_path=ssh_key_path,
            provider=provider,
            status="inactive",
        )
        session.add(srv)

    # Test SSH connectivity
    info(f"Testing SSH connection to {user}@{host}:{port}...")
    client = SSHClient(host=host, user=user, port=port, key_path=ssh_key_path)
    if client.test_connection():
        success(f"Server '{name}' added and SSH connection verified")
    else:
        success(f"Server '{name}' added (SSH connection could not be verified — check credentials)")


@server.command("list")
@click.option("--tag", "filter_tag", default=None, help="Filter by tag")
def list_servers(filter_tag: str | None) -> None:
    """List all registered servers."""
    init_db()
    with get_session() as session:
        q = session.query(Server).order_by(Server.name)
        if filter_tag:
            q = q.join(ServerTag).filter(ServerTag.tag == filter_tag)
        servers = q.all()
        if not servers:
            info("No servers found.")
            return
        rows = [
            (
                s.name,
                s.host,
                s.user,
                s.port,
                s.status,
                s.provider or "—",
                ", ".join(t.tag for t in s.tags) or "—",
            )
            for s in servers
        ]
    print_table("Servers", ["Name", "Host", "User", "Port", "Status", "Provider", "Tags"], rows)


@server.command()
@click.argument("name")
@click.option("--force", is_flag=True, help="Skip confirmation")
def remove(name: str, force: bool) -> None:
    """Remove a registered server."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            error(f"Server '{name}' not found")
            raise SystemExit(1)
        app_count = len(srv.apps)
        if app_count and not force:
            click.confirm(f"Server '{name}' has {app_count} app(s). Remove anyway?", abort=True)
        session.delete(srv)
    success(f"Server '{name}' removed")


@server.command()
@click.argument("name")
def provision(name: str) -> None:
    """Provision a server with Docker, Caddy, and security hardening."""
    init_db()
    srv = _get_server(name)

    with status_spinner(f"Provisioning {srv.name} ({srv.host})"):
        with _ssh_for_server(srv) as ssh:
            from cli.core.provisioner import provision_server

            provision_server(ssh)

    with get_session() as session:
        s = session.query(Server).filter(Server.name == name).first()
        if s:
            s.status = "active"

    success(f"Server '{name}' provisioned and active")


@server.command()
@click.argument("name")
def status(name: str) -> None:
    """Show server resource usage and Docker status."""
    init_db()
    srv = _get_server(name)

    with _ssh_for_server(srv) as ssh:
        # Gather system info
        uptime = ssh.run_checked("uptime -p").strip()
        mem = ssh.run_checked("free -h | awk '/Mem:/{print $3\"/\"$2}'").strip()
        disk_cmd = 'df -h / | awk \'NR==2{print $3"/"$2" ("$5" used)"}\''
        disk = ssh.run_checked(disk_cmd).strip()
        containers = ssh.run_checked(
            "docker ps --format '{{.Names}}\\t{{.Status}}' 2>/dev/null || echo 'Docker not running'"
        ).strip()

    info(f"Server: {srv.name} ({srv.host})")
    info(f"Uptime: {uptime}")
    info(f"Memory: {mem}")
    info(f"Disk:   {disk}")
    info(f"Containers:\n{containers}")


@server.command()
@click.argument("name")
@click.option("--hours", default=24, show_default=True, help="Hours of history to show")
def metrics(name: str, hours: int) -> None:
    """Show recent server metric history."""
    from datetime import UTC, datetime, timedelta

    from cli.models.server_metric import ServerMetric

    init_db()
    srv = _get_server(name)
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    with get_session() as session:
        recs = (
            session.query(ServerMetric)
            .filter(
                ServerMetric.server_id == srv.id,
                ServerMetric.recorded_at >= cutoff,
            )
            .order_by(ServerMetric.recorded_at.desc())
            .limit(50)
            .all()
        )
        if not recs:
            info(f"No metrics recorded for '{name}' in the last {hours}h.")
            return
        rows = [
            (
                r.recorded_at.strftime("%Y-%m-%d %H:%M:%S"),
                f"{r.cpu_percent:.1f}%" if r.cpu_percent is not None else "—",
                f"{r.mem_percent:.1f}%" if r.mem_percent is not None else "—",
                f"{r.disk_percent:.1f}%" if r.disk_percent is not None else "—",
            )
            for r in recs
        ]
    print_table(f"Metrics for {name} (last {hours}h)", ["Time", "CPU", "Memory", "Disk"], rows)


@server.command()
@click.argument("name")
def ssh(name: str) -> None:
    """Open an interactive SSH session to the server."""
    import subprocess

    srv = _get_server(name)
    cmd = ["ssh", f"{srv.user}@{srv.host}", "-p", str(srv.port)]
    if srv.ssh_key_path:
        cmd.extend(["-i", srv.ssh_key_path])
    info(f"Connecting to {srv.user}@{srv.host}...")
    subprocess.run(cmd)


@server.command("tag")
@click.argument("name")
@click.option("--add", "add_tag", default=None, help="Tag to add")
@click.option("--remove", "remove_tag", default=None, help="Tag to remove")
def tag(name: str, add_tag: str | None, remove_tag: str | None) -> None:
    """Manage tags on a server."""
    init_db()
    if not add_tag and not remove_tag:
        # List tags
        with get_session() as session:
            srv = session.query(Server).filter(Server.name == name).first()
            if not srv:
                error(f"Server '{name}' not found")
                raise SystemExit(1)
            tags = [t.tag for t in srv.tags]
        if tags:
            info(f"Tags for '{name}': {', '.join(tags)}")
        else:
            info(f"No tags for '{name}'")
        return

    with get_session() as session:
        srv = session.query(Server).filter(Server.name == name).first()
        if not srv:
            error(f"Server '{name}' not found")
            raise SystemExit(1)
        if add_tag:
            existing = (
                session.query(ServerTag)
                .filter(ServerTag.server_id == srv.id, ServerTag.tag == add_tag)
                .first()
            )
            if existing:
                info(f"Tag '{add_tag}' already exists on '{name}'")
                return
            session.add(ServerTag(server_id=srv.id, tag=add_tag))
            success(f"Tag '{add_tag}' added to '{name}'")
        if remove_tag:
            existing = (
                session.query(ServerTag)
                .filter(ServerTag.server_id == srv.id, ServerTag.tag == remove_tag)
                .first()
            )
            if not existing:
                error(f"Tag '{remove_tag}' not found on '{name}'")
                raise SystemExit(1)
            session.delete(existing)
            success(f"Tag '{remove_tag}' removed from '{name}'")
