import click

from cli.core.console import error, info, print_table, success, status_spinner
from cli.core.database import get_session, init_db
from cli.core.exceptions import SSHConnectionError, ServerNotFoundError
from cli.core.ssh import SSHClient
from cli.models.server import Server


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
@click.option("--provider", default=None, help="Cloud provider label (hetzner, digitalocean, etc.)")
def add(name: str, host: str, user: str, port: int, ssh_key_path: str | None, provider: str | None) -> None:
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
def list_servers() -> None:
    """List all registered servers."""
    init_db()
    with get_session() as session:
        servers = session.query(Server).order_by(Server.name).all()
        if not servers:
            info("No servers registered. Use 'infrakt server add' to add one.")
            return
        rows = [
            (s.name, s.host, s.user, s.port, s.status, s.provider or "—")
            for s in servers
        ]
    print_table("Servers", ["Name", "Host", "User", "Port", "Status", "Provider"], rows)


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
            click.confirm(
                f"Server '{name}' has {app_count} app(s). Remove anyway?", abort=True
            )
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
        disk = ssh.run_checked("df -h / | awk 'NR==2{print $3\"/\"$2\" (\"$5\" used)\"}'").strip()
        containers = ssh.run_checked("docker ps --format '{{.Names}}\\t{{.Status}}' 2>/dev/null || echo 'Docker not running'").strip()

    info(f"Server: {srv.name} ({srv.host})")
    info(f"Uptime: {uptime}")
    info(f"Memory: {mem}")
    info(f"Disk:   {disk}")
    info(f"Containers:\n{containers}")


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
