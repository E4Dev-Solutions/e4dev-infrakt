import click

from cli.core.console import console, error, info, print_table, success, status_spinner
from cli.core.database import get_session, init_db
from cli.core.exceptions import ServerNotFoundError
from cli.core.proxy_manager import add_domain, get_status, list_domains, reload_proxy, remove_domain
from cli.core.ssh import SSHClient
from cli.models.server import Server


def _get_ssh(server_name: str) -> SSHClient:
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            raise ServerNotFoundError(f"Server '{server_name}' not found")
        return SSHClient(host=srv.host, user=srv.user, port=srv.port, key_path=srv.ssh_key_path)


@click.group()
def proxy() -> None:
    """Manage reverse proxy (Caddy) configuration."""


@proxy.command()
@click.argument("server_name")
def setup(server_name: str) -> None:
    """Initialize Caddy on a server (done automatically during provisioning)."""
    ssh = _get_ssh(server_name)
    with status_spinner("Setting up Caddy"):
        with ssh:
            ssh.run_checked("mkdir -p /opt/infrakt/caddy")
            ssh.run(
                "test -f /opt/infrakt/caddy/Caddyfile || "
                "echo '# Managed by infrakt' > /opt/infrakt/caddy/Caddyfile"
            )
            ssh.run_checked(
                "mkdir -p /etc/caddy && "
                "echo 'import /opt/infrakt/caddy/Caddyfile' > /etc/caddy/Caddyfile && "
                "systemctl restart caddy"
            )
    success(f"Caddy configured on '{server_name}'")


@proxy.command("add")
@click.argument("domain")
@click.option("--server", "server_name", required=True)
@click.option("--port", required=True, type=int, help="Local port to proxy to")
def add_route(domain: str, server_name: str, port: int) -> None:
    """Add a domain reverse proxy route."""
    ssh = _get_ssh(server_name)
    with ssh:
        add_domain(ssh, domain, port)
    success(f"Added proxy: {domain} -> localhost:{port}")


@proxy.command("remove")
@click.argument("domain")
@click.option("--server", "server_name", required=True)
def remove_route(domain: str, server_name: str) -> None:
    """Remove a domain reverse proxy route."""
    ssh = _get_ssh(server_name)
    with ssh:
        remove_domain(ssh, domain)
    success(f"Removed proxy for {domain}")


@proxy.command("domains")
@click.argument("server_name")
def domains(server_name: str) -> None:
    """List all proxy routes on a server."""
    ssh = _get_ssh(server_name)
    with ssh:
        entries = list_domains(ssh)
    if not entries:
        info("No proxy routes configured.")
        return
    rows = [(d, p) for d, p in entries]
    print_table("Proxy Routes", ["Domain", "Port"], rows)


@proxy.command("status")
@click.argument("server_name")
def proxy_status(server_name: str) -> None:
    """Show Caddy service status."""
    ssh = _get_ssh(server_name)
    with ssh:
        output = get_status(ssh)
    console.print(output)


@proxy.command("reload")
@click.argument("server_name")
def reload(server_name: str) -> None:
    """Reload Caddy configuration."""
    ssh = _get_ssh(server_name)
    with ssh:
        reload_proxy(ssh)
    success("Caddy configuration reloaded")
