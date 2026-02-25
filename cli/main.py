import click

from cli.core.config import ensure_config_dir
from cli.core.console import success
from cli.core.database import init_db


@click.group()
@click.version_option(version="0.1.0", prog_name="infrakt")
def cli() -> None:
    """infrakt — A self-hosted PaaS for multi-server, multi-app deployments."""


@cli.command()
def init() -> None:
    """Initialize infrakt configuration and database."""
    config_dir = ensure_config_dir()
    init_db()
    success(f"Initialized infrakt at {config_dir}")


# Register command groups
from cli.commands.app import app  # noqa: E402
from cli.commands.db import db  # noqa: E402
from cli.commands.env import env  # noqa: E402
from cli.commands.proxy import proxy  # noqa: E402
from cli.commands.server import server  # noqa: E402
from cli.commands.webhook import webhook  # noqa: E402

cli.add_command(server)
cli.add_command(app)
cli.add_command(env)
cli.add_command(db)
cli.add_command(proxy)
cli.add_command(webhook)

if __name__ == "__main__":
    cli()
