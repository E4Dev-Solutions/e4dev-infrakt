import json
import shlex

import click

from cli.core.config import ENVS_DIR, ensure_config_dir
from cli.core.console import error, info, print_table, success
from cli.core.crypto import decrypt, encrypt
from cli.core.database import get_session, init_db
from cli.core.deployer import _validate_name
from cli.core.exceptions import AppNotFoundError
from cli.models.app import App
from cli.models.server import Server


def _get_app_id(app_name: str, server_name: str | None) -> int:
    with get_session() as session:
        q = session.query(App).filter(App.name == app_name)
        if server_name:
            q = q.join(Server).filter(Server.name == server_name)
        app_obj = q.first()
        if not app_obj:
            raise AppNotFoundError(f"App '{app_name}' not found")
        return app_obj.id


def _env_file(app_id: int):
    ensure_config_dir()
    return ENVS_DIR / f"{app_id}.json"


def _load_env(app_id: int) -> dict[str, str]:
    path = _env_file(app_id)
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def _save_env(app_id: int, data: dict[str, str]) -> None:
    _env_file(app_id).write_text(json.dumps(data, indent=2))


@click.group()
def env() -> None:
    """Manage app environment variables."""


@env.command("set")
@click.argument("app_name")
@click.argument("pairs", nargs=-1, required=True)
@click.option("--server", "server_name", default=None)
def set_env(app_name: str, pairs: tuple[str, ...], server_name: str | None) -> None:
    """Set environment variables (KEY=VALUE pairs)."""
    init_db()
    app_id = _get_app_id(app_name, server_name)
    data = _load_env(app_id)

    for pair in pairs:
        if "=" not in pair:
            error(f"Invalid format: '{pair}'. Expected KEY=VALUE")
            raise SystemExit(1)
        key, value = pair.split("=", 1)
        data[key] = encrypt(value)

    _save_env(app_id, data)
    success(f"Set {len(pairs)} variable(s) for '{app_name}'")
    info("Run 'infrakt app deploy' to apply changes to the running app.")


@env.command("get")
@click.argument("app_name")
@click.argument("key")
@click.option("--server", "server_name", default=None)
def get_env(app_name: str, key: str, server_name: str | None) -> None:
    """Get the value of an environment variable."""
    init_db()
    app_id = _get_app_id(app_name, server_name)
    data = _load_env(app_id)

    if key not in data:
        error(f"Variable '{key}' not set for '{app_name}'")
        raise SystemExit(1)

    click.echo(decrypt(data[key]))


@env.command("list")
@click.argument("app_name")
@click.option("--server", "server_name", default=None)
@click.option("--show-values", is_flag=True, help="Show decrypted values")
def list_env(app_name: str, server_name: str | None, show_values: bool) -> None:
    """List environment variables for an app."""
    init_db()
    app_id = _get_app_id(app_name, server_name)
    data = _load_env(app_id)

    if not data:
        info(f"No environment variables set for '{app_name}'")
        return

    rows = []
    for key in sorted(data.keys()):
        value = decrypt(data[key]) if show_values else "••••••••"
        rows.append((key, value))

    print_table(f"Environment: {app_name}", ["Key", "Value"], rows)


@env.command("delete")
@click.argument("app_name")
@click.argument("key")
@click.option("--server", "server_name", default=None)
def delete_env(app_name: str, key: str, server_name: str | None) -> None:
    """Delete an environment variable."""
    init_db()
    app_id = _get_app_id(app_name, server_name)
    data = _load_env(app_id)

    if key not in data:
        error(f"Variable '{key}' not set for '{app_name}'")
        raise SystemExit(1)

    del data[key]
    _save_env(app_id, data)
    success(f"Deleted '{key}' from '{app_name}'")


@env.command("push")
@click.argument("app_name")
@click.option("--server", "server_name", default=None)
def push_env(app_name: str, server_name: str | None) -> None:
    """Push environment variables to server and restart the app."""
    init_db()

    with get_session() as session:
        q = session.query(App).filter(App.name == app_name)
        if server_name:
            q = q.join(Server).filter(Server.name == server_name)
        app_obj = q.first()
        if not app_obj:
            raise AppNotFoundError(f"App '{app_name}' not found")

        from cli.core.ssh import SSHClient
        ssh = SSHClient.from_server(app_obj.server)
        app_id = app_obj.id

    data = _load_env(app_id)
    lines = [f"{k}={decrypt(v)}" for k, v in sorted(data.items())]
    env_content = "\n".join(lines) + "\n" if lines else ""

    _validate_name(app_name, "app name")
    app_path = f"/opt/infrakt/apps/{app_name}"
    q_path = shlex.quote(app_path)
    with ssh:
        ssh.upload_string(env_content, f"{app_path}/.env")
        ssh.run_checked(f"cd {q_path} && docker compose restart", timeout=60)

    success(f"Pushed {len(data)} variable(s) to '{app_name}' and restarted")
