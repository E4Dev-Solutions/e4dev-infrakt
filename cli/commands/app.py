from datetime import datetime

import click

from cli.core.console import console, error, info, print_table, status_spinner, success
from cli.core.crypto import env_content_for_app
from cli.core.database import get_session, init_db
from cli.core.deployer import deploy_app, destroy_app, get_logs, restart_app, stop_app
from cli.core.exceptions import AppNotFoundError, ServerNotFoundError
from cli.core.proxy_manager import add_domain, remove_domain
from cli.core.ssh import SSHClient
from cli.models.app import App
from cli.models.deployment import Deployment
from cli.models.server import Server


def _resolve_server(
    session: object, server_name: str | None, app_name: str | None = None
) -> Server:
    """Resolve server by name, or by looking up the app's server."""
    if server_name:
        srv: Server | None = session.query(Server).filter(Server.name == server_name).first()  # type: ignore[attr-defined]
        if not srv:
            raise ServerNotFoundError(f"Server '{server_name}' not found")
        return srv
    if app_name:
        app_obj: App | None = session.query(App).filter(App.name == app_name).first()  # type: ignore[attr-defined]
        if app_obj:
            return app_obj.server
    raise click.UsageError("Please specify --server or ensure the app name is unique")


def _get_app(session: object, app_name: str, server_name: str | None) -> App:
    q = session.query(App).filter(App.name == app_name)  # type: ignore[attr-defined]
    if server_name:
        q = q.join(Server).filter(Server.name == server_name)
    app_obj: App | None = q.first()
    if not app_obj:
        raise AppNotFoundError(f"App '{app_name}' not found")
    return app_obj


def _ssh_for_server(srv: Server) -> SSHClient:
    result = SSHClient.from_server(srv)
    return result


@click.group()
def app() -> None:
    """Manage application deployments."""


@app.command()
@click.option("--server", "server_name", required=True, help="Target server name")
@click.option("--name", required=True, help="App name")
@click.option("--domain", default=None, help="Domain for the app (e.g. api.example.com)")
@click.option("--port", default=3000, help="Container port the app listens on")
@click.option("--git", "git_repo", default=None, help="Git repository URL")
@click.option("--branch", default="main", help="Git branch")
@click.option("--image", default=None, help="Docker image (e.g. nginx:latest)")
def create(
    server_name: str,
    name: str,
    domain: str | None,
    port: int,
    git_repo: str | None,
    branch: str,
    image: str | None,
) -> None:
    """Create a new app on a server."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            error(f"Server '{server_name}' not found")
            raise SystemExit(1)

        existing = session.query(App).filter(App.name == name, App.server_id == srv.id).first()
        if existing:
            error(f"App '{name}' already exists on server '{server_name}'")
            raise SystemExit(1)

        app_type = "image" if image else "git" if git_repo else "compose"
        new_app = App(
            name=name,
            server_id=srv.id,
            domain=domain,
            port=port,
            git_repo=git_repo,
            branch=branch,
            image=image,
            app_type=app_type,
            status="stopped",
        )
        session.add(new_app)

    success(
        f"App '{name}' created on server '{server_name}'. "
        f"Use 'infrakt app deploy {name}' to deploy."
    )


@app.command()
@click.argument("name")
@click.option(
    "--server",
    "server_name",
    default=None,
    help="Server name (optional if app name is unique)",
)
def deploy(name: str, server_name: str | None) -> None:
    """Deploy or redeploy an app."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server

        # Create deployment record
        dep = Deployment(app_id=app_obj.id, status="in_progress")
        session.add(dep)
        session.flush()
        dep_id = dep.id
        app_id = app_obj.id
        app_port = app_obj.port
        app_git = app_obj.git_repo
        app_branch = app_obj.branch
        app_image = app_obj.image
        app_domain = app_obj.domain

        # Get env content
        env_content = env_content_for_app(app_id)

        ssh = _ssh_for_server(srv)

    try:
        with status_spinner(f"Deploying '{name}'"):
            # Ensure infrakt network exists
            ssh.connect()
            ssh.run("docker network create infrakt 2>/dev/null || true")

            log = deploy_app(
                ssh,
                name,
                git_repo=app_git,
                branch=app_branch,
                image=app_image,
                port=app_port,
                env_content=env_content,
            )

            # Set up reverse proxy if domain is configured
            if app_domain:
                add_domain(ssh, app_domain, app_port)

        ssh.close()

        # Update records
        with get_session() as session:
            dep_record = session.query(Deployment).filter(Deployment.id == dep_id).first()
            if dep_record is not None:
                dep_record.status = "success"
                dep_record.log = log
                dep_record.finished_at = datetime.utcnow()
            app_record = session.query(App).filter(App.id == app_id).first()
            if app_record is not None:
                app_record.status = "running"

        success(f"App '{name}' deployed successfully")

    except Exception as exc:
        with get_session() as session:
            dep_record = session.query(Deployment).filter(Deployment.id == dep_id).first()
            if dep_record is not None:
                dep_record.status = "failed"
                dep_record.log = str(exc)
                dep_record.finished_at = datetime.utcnow()
            app_record = session.query(App).filter(App.id == app_id).first()
            if app_record is not None:
                app_record.status = "error"
        error(f"Deployment failed: {exc}")
        raise SystemExit(1)


@app.command("list")
@click.option("--server", "server_name", default=None, help="Filter by server")
def list_apps(server_name: str | None) -> None:
    """List all apps."""
    init_db()
    with get_session() as session:
        q = session.query(App).join(Server)
        if server_name:
            q = q.filter(Server.name == server_name)
        apps = q.order_by(Server.name, App.name).all()
        if not apps:
            info("No apps found.")
            return
        rows = [
            (a.name, a.server.name, a.domain or "—", a.port, a.status, a.app_type)
            for a in apps
        ]
    print_table("Apps", ["Name", "Server", "Domain", "Port", "Status", "Type"], rows)


@app.command()
@click.argument("name")
@click.option("--server", "server_name", default=None)
@click.option("--lines", default=100, help="Number of log lines")
def logs(name: str, server_name: str | None, lines: int) -> None:
    """View app container logs."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server
        ssh = _ssh_for_server(srv)

    with ssh:
        output = get_logs(ssh, name, lines=lines)
    console.print(output)


@app.command()
@click.argument("name")
@click.option("--server", "server_name", default=None)
def restart(name: str, server_name: str | None) -> None:
    """Restart an app's containers."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server
        ssh = _ssh_for_server(srv)

    with status_spinner(f"Restarting '{name}'"):
        with ssh:
            restart_app(ssh, name)

    success(f"App '{name}' restarted")


@app.command()
@click.argument("name")
@click.option("--server", "server_name", default=None)
def stop(name: str, server_name: str | None) -> None:
    """Stop an app's containers."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server
        ssh = _ssh_for_server(srv)
        app_id = app_obj.id

    with status_spinner(f"Stopping '{name}'"):
        with ssh:
            stop_app(ssh, name)

    with get_session() as session:
        a = session.query(App).filter(App.id == app_id).first()
        if a:
            a.status = "stopped"

    success(f"App '{name}' stopped")


@app.command()
@click.argument("name")
@click.option("--server", "server_name", default=None)
@click.option("--force", is_flag=True, help="Skip confirmation")
def destroy(name: str, server_name: str | None, force: bool) -> None:
    """Destroy an app and remove all its data from the server."""
    init_db()
    if not force:
        click.confirm(f"Destroy app '{name}' and all its data?", abort=True)

    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server
        app_domain = app_obj.domain
        ssh = _ssh_for_server(srv)
        app_id = app_obj.id

    with status_spinner(f"Destroying '{name}'"):
        with ssh:
            destroy_app(ssh, name)
            if app_domain:
                remove_domain(ssh, app_domain)

    with get_session() as session:
        app_record = session.query(App).filter(App.id == app_id).first()
        if app_record is not None:
            session.delete(app_record)

    success(f"App '{name}' destroyed")
