import secrets
import shlex

import click

from cli.core.backup import (
    backup_database,
    install_backup_cron,
    remove_backup_cron,
    restore_database,
)
from cli.core.backup import (
    list_backups as list_backups_fn,
)
from cli.core.config import BACKUPS_DIR
from cli.core.console import error, info, print_table, status_spinner, success
from cli.core.database import get_session, init_db
from cli.core.deployer import _validate_name
from cli.core.exceptions import ServerNotFoundError
from cli.core.ssh import SSHClient
from cli.models.app import App
from cli.models.server import Server

DB_TEMPLATES = {
    "postgres": {
        "image": "postgres:{version}",
        "port": 5432,
        "env": {
            "POSTGRES_DB": "{name}",
            "POSTGRES_USER": "{name}",
            "POSTGRES_PASSWORD": "{password}",
        },
        "volume": "{name}_data:/var/lib/postgresql/data",
    },
    "mysql": {
        "image": "mysql:{version}",
        "port": 3306,
        "env": {
            "MYSQL_DATABASE": "{name}",
            "MYSQL_USER": "{name}",
            "MYSQL_PASSWORD": "{password}",
            "MYSQL_ROOT_PASSWORD": "{password}",
        },
        "volume": "{name}_data:/var/lib/mysql",
    },
    "redis": {
        "image": "redis:{version}",
        "port": 6379,
        "env": {},
        "volume": "{name}_data:/data",
    },
    "mongo": {
        "image": "mongo:{version}",
        "port": 27017,
        "env": {
            "MONGO_INITDB_ROOT_USERNAME": "{name}",
            "MONGO_INITDB_ROOT_PASSWORD": "{password}",
        },
        "volume": "{name}_data:/data/db",
    },
}

DEFAULT_VERSIONS = {
    "postgres": "16",
    "mysql": "8",
    "redis": "7-alpine",
    "mongo": "7",
}


def _generate_db_compose(db_type: str, name: str, version: str, password: str) -> str:
    from cli.core.compose_renderer import render_db_compose

    tpl = DB_TEMPLATES[db_type]
    image_template = tpl.get("image")
    volume_template = tpl.get("volume")
    if not isinstance(image_template, str) or not isinstance(volume_template, str):
        raise ValueError("Invalid template")
    image = image_template.format(version=version)
    volume = volume_template.format(name=name)

    env_dict = tpl.get("env")
    if not isinstance(env_dict, dict):
        env_dict = {}
    env_vars = {k: v.format(name=name, password=password) for k, v in env_dict.items()}

    port_val = tpl.get("port")
    if not isinstance(port_val, int):
        port_val = 5432

    return render_db_compose(
        db_type=db_type,
        name=name,
        image=image,
        port=port_val,
        env_vars=env_vars,
        volume=volume,
    )


def _connection_string(db_type: str, name: str, password: str) -> str:
    tpl = DB_TEMPLATES[db_type]
    port = tpl["port"]
    if db_type == "postgres":
        return f"postgresql://{name}:{password}@localhost:{port}/{name}"
    elif db_type == "mysql":
        return f"mysql://{name}:{password}@localhost:{port}/{name}"
    elif db_type == "redis":
        return f"redis://localhost:{port}"
    elif db_type == "mongo":
        return f"mongodb://{name}:{password}@localhost:{port}"
    return f"localhost:{port}"


@click.group()
def db() -> None:
    """Manage database services on servers."""


@db.command()
@click.option("--server", "server_name", required=True, help="Target server")
@click.option("--name", required=True, help="Database service name")
@click.option(
    "--type",
    "db_type",
    required=True,
    type=click.Choice(list(DB_TEMPLATES.keys())),
    help="Database type",
)
@click.option(
    "--version",
    default=None,
    help="Database version (default: latest stable)",
)
def create(server_name: str, name: str, db_type: str, version: str | None) -> None:
    """Create a database service on a server."""
    init_db()
    version = version or DEFAULT_VERSIONS.get(db_type, "latest")
    password = secrets.token_urlsafe(24)

    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            raise ServerNotFoundError(f"Server '{server_name}' not found")

        # Store as an app with type "database"
        existing = session.query(App).filter(App.name == name, App.server_id == srv.id).first()
        if existing:
            error(f"Service '{name}' already exists on '{server_name}'")
            raise SystemExit(1)

        db_app = App(
            name=name,
            server_id=srv.id,
            port=DB_TEMPLATES[db_type]["port"],
            app_type=f"db:{db_type}",
            status="stopped",
        )
        session.add(db_app)
        session.flush()

        ssh = SSHClient.from_server(srv)

    _validate_name(name, "database name")
    compose = _generate_db_compose(db_type, name, version, password)
    app_path = f"/opt/infrakt/apps/{name}"
    q_path = shlex.quote(app_path)

    with status_spinner(f"Creating {db_type} database '{name}'"):
        with ssh:
            ssh.run("docker network create infrakt 2>/dev/null || true")
            ssh.run_checked(f"mkdir -p {q_path}")
            ssh.upload_string(compose, f"{app_path}/docker-compose.yml")
            ssh.run_checked(f"cd {q_path} && docker compose up -d", timeout=120)

    with get_session() as session:
        a = session.query(App).filter(App.name == name).first()
        if a:
            a.status = "running"

    conn = _connection_string(db_type, name, password)
    success(f"Database '{name}' ({db_type}) created on '{server_name}'")
    info(f"Connection string: {conn}")
    info("Save this connection string — the password is not stored locally.")


@db.command()
@click.argument("name")
@click.option("--server", "server_name", required=True, help="Server name")
@click.option("--force", is_flag=True)
def destroy(name: str, server_name: str, force: bool) -> None:
    """Destroy a database service and its data."""
    init_db()
    if not force:
        click.confirm(f"Destroy database '{name}' and ALL its data?", abort=True)

    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            raise ServerNotFoundError(f"Server '{server_name}' not found")
        ssh = SSHClient.from_server(srv)

    _validate_name(name, "database name")
    app_path = f"/opt/infrakt/apps/{name}"
    q_path = shlex.quote(app_path)
    with status_spinner(f"Destroying database '{name}'"):
        with ssh:
            ssh.run(f"cd {q_path} && docker compose down -v --remove-orphans", timeout=60)
            ssh.run_checked(f"rm -rf {q_path}")

    with get_session() as session:
        a = session.query(App).filter(App.name == name).first()
        if a:
            session.delete(a)

    success(f"Database '{name}' destroyed")


@db.command("list")
@click.option("--server", "server_name", default=None)
def list_dbs(server_name: str | None) -> None:
    """List database services."""
    init_db()
    with get_session() as session:
        q = session.query(App).filter(App.app_type.like("db:%"))
        if server_name:
            q = q.join(Server).filter(Server.name == server_name)
        dbs = q.order_by(App.name).all()
        if not dbs:
            info("No database services found.")
            return
        rows = [(d.name, d.server.name, d.app_type.split(":", 1)[1], d.port, d.status) for d in dbs]
    print_table("Databases", ["Name", "Server", "Type", "Port", "Status"], rows)


@db.command()
@click.argument("name")
@click.option("--server", "server_name", required=True, help="Server name")
@click.option(
    "--output", "-o", default=None, help="Local output path (default: ~/.infrakt/backups/)"
)
def backup(name: str, server_name: str, output: str | None) -> None:
    """Back up a database to a local file."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            raise ServerNotFoundError(f"Server '{server_name}' not found")
        db_app = (
            session.query(App)
            .filter(App.name == name, App.server_id == srv.id, App.app_type.like("db:%"))
            .first()
        )
        if not db_app:
            error(f"Database '{name}' not found on '{server_name}'")
            raise SystemExit(1)
        ssh = SSHClient.from_server(srv)

    with status_spinner(f"Backing up database '{name}'"):
        with ssh:
            remote_path = backup_database(ssh, db_app)
            # Download to local
            BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
            filename = remote_path.rsplit("/", 1)[-1]
            local_path = output or str(BACKUPS_DIR / filename)
            ssh.download(remote_path, local_path)

    success(f"Database '{name}' backed up")
    info(f"Local file: {local_path}")


@db.command()
@click.argument("name")
@click.argument("file", type=click.Path(exists=True))
@click.option("--server", "server_name", required=True, help="Server name")
def restore(name: str, file: str, server_name: str) -> None:
    """Restore a database from a backup file."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            raise ServerNotFoundError(f"Server '{server_name}' not found")
        db_app = (
            session.query(App)
            .filter(App.name == name, App.server_id == srv.id, App.app_type.like("db:%"))
            .first()
        )
        if not db_app:
            error(f"Database '{name}' not found on '{server_name}'")
            raise SystemExit(1)
        ssh = SSHClient.from_server(srv)

    remote_path = f"/opt/infrakt/backups/{file.rsplit('/', 1)[-1]}"

    with status_spinner(f"Restoring database '{name}'"):
        with ssh:
            ssh.run_checked("mkdir -p /opt/infrakt/backups")
            ssh.upload(file, remote_path)
            restore_database(ssh, db_app, remote_path)

    success(f"Database '{name}' restored from {file}")


def _validate_cron(cron: str) -> None:
    """Validate that a cron expression has exactly 5 fields."""
    parts = cron.strip().split()
    if len(parts) != 5:
        error("Cron expression must have exactly 5 fields (e.g. '0 2 * * *')")
        raise SystemExit(1)


@db.command("schedule-backup")
@click.argument("name")
@click.option("--server", "server_name", required=True, help="Server name")
@click.option("--cron", required=True, help='Cron expression, e.g. "0 2 * * *"')
@click.option("--retention", default=7, type=int, help="Days to keep old backups (default: 7)")
def schedule_backup(name: str, server_name: str, cron: str, retention: int) -> None:
    """Schedule automatic backups for a database."""
    init_db()
    _validate_cron(cron)

    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            raise ServerNotFoundError(f"Server '{server_name}' not found")
        db_app = (
            session.query(App)
            .filter(App.name == name, App.server_id == srv.id, App.app_type.like("db:%"))
            .first()
        )
        if not db_app:
            error(f"Database '{name}' not found on '{server_name}'")
            raise SystemExit(1)
        ssh = SSHClient.from_server(srv)

    _validate_name(name, "database name")
    with status_spinner(f"Scheduling backups for '{name}'"):
        with ssh:
            install_backup_cron(ssh, db_app, cron, retention)

    with get_session() as session:
        a = session.query(App).filter(App.name == name).first()
        if a:
            a.backup_schedule = cron

    success(f"Scheduled backups for '{name}' with cron '{cron}'")
    info(f"Retention: {retention} days")


@db.command("unschedule-backup")
@click.argument("name")
@click.option("--server", "server_name", required=True, help="Server name")
def unschedule_backup(name: str, server_name: str) -> None:
    """Remove scheduled backups for a database."""
    init_db()

    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            raise ServerNotFoundError(f"Server '{server_name}' not found")
        db_app = (
            session.query(App)
            .filter(App.name == name, App.server_id == srv.id, App.app_type.like("db:%"))
            .first()
        )
        if not db_app:
            error(f"Database '{name}' not found on '{server_name}'")
            raise SystemExit(1)
        ssh = SSHClient.from_server(srv)

    _validate_name(name, "database name")
    with status_spinner(f"Removing scheduled backups for '{name}'"):
        with ssh:
            remove_backup_cron(ssh, db_app)

    with get_session() as session:
        a = session.query(App).filter(App.name == name).first()
        if a:
            a.backup_schedule = None

    success(f"Removed scheduled backups for '{name}'")


@db.command()
@click.argument("name")
@click.option("--server", "server_name", required=True, help="Server name")
def backups(name: str, server_name: str) -> None:
    """List available backups for a database."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            raise ServerNotFoundError(f"Server '{server_name}' not found")
        db_app = (
            session.query(App)
            .filter(App.name == name, App.server_id == srv.id, App.app_type.like("db:%"))
            .first()
        )
        if not db_app:
            error(f"Database '{name}' not found on '{server_name}'")
            raise SystemExit(1)
        ssh = SSHClient.from_server(srv)

    with status_spinner(f"Listing backups for '{name}'"):
        with ssh:
            backup_list = list_backups_fn(ssh, db_app)

    if not backup_list:
        info("No backups found.")
        return

    rows = [(b["filename"], b["size"], b["modified"]) for b in backup_list]
    print_table(f"Backups for {name}", ["Filename", "Size", "Date"], rows)


@db.command("info")
@click.argument("name")
@click.option("--server", "server_name", required=True, help="Server name")
def info_cmd(name: str, server_name: str) -> None:
    """Show database details."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            raise ServerNotFoundError(f"Server '{server_name}' not found")
        db_app = (
            session.query(App)
            .filter(App.name == name, App.server_id == srv.id, App.app_type.like("db:%"))
            .first()
        )
        if not db_app:
            error(f"Database '{name}' not found on '{server_name}'")
            raise SystemExit(1)

        db_type = db_app.app_type.split(":", 1)[1]
        from rich.panel import Panel
        from rich.table import Table

        from cli.core.console import console

        t = Table(show_header=False, box=None, pad_edge=False)
        t.add_row("Name", db_app.name)
        t.add_row("Server", srv.name)
        t.add_row("Type", db_type)
        t.add_row("Port", str(db_app.port))
        t.add_row("Status", db_app.status)
        t.add_row("Schedule", db_app.backup_schedule or "None")
        t.add_row("Created", str(db_app.created_at))
        console.print(Panel(t, title=f"Database: {name}"))

        ssh = SSHClient.from_server(srv)

    # Fetch live stats
    try:
        with ssh:
            from cli.core.db_stats import get_database_stats

            stats = get_database_stats(ssh, name, db_type)
        if any(v is not None for v in stats.values()):
            info("")  # blank line
            stats_rows = []
            if stats["version"]:
                stats_rows.append(("Version", stats["version"]))
            if stats["disk_size"]:
                stats_rows.append(("Disk Size", stats["disk_size"]))
            if stats["active_connections"] is not None:
                stats_rows.append(("Connections", str(stats["active_connections"])))
            if stats["uptime"]:
                stats_rows.append(("Uptime", stats["uptime"]))
            if stats_rows:
                print_table("Live Stats", ["Metric", "Value"], stats_rows)
    except Exception:
        pass  # stats are best-effort
