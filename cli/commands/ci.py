"""CI/CD integration commands."""

from __future__ import annotations

import click

from cli.core.console import error, info, print_table, success
from cli.core.database import get_session, init_db
from cli.core.deploy_keys import (
    generate_deploy_key,
    list_deploy_keys,
    revoke_deploy_key,
)
from cli.models.app import App


@click.group()
def ci() -> None:
    """CI/CD integration commands."""


@ci.command("generate-key")
@click.option("--label", required=True, help="Label for this deploy key (e.g. 'github-actions')")
def generate_key(label: str) -> None:
    """Generate a restricted API key for CI/CD use."""
    try:
        key = generate_deploy_key(label)
    except ValueError as exc:
        error(str(exc))
        raise SystemExit(1)
    success(f"Deploy key generated with label '{label}'")
    info(f"Key: {key}")
    info("Save this key — it will not be shown again.")


@ci.command("list-keys")
def list_keys() -> None:
    """List active deploy keys."""
    keys = list_deploy_keys()
    if not keys:
        info("No deploy keys found.")
        return
    rows = [(k["label"], k["created_at"], ", ".join(k.get("scopes", []))) for k in keys]
    print_table("Deploy Keys", ["Label", "Created", "Scopes"], rows)


@ci.command("revoke-key")
@click.argument("label")
def revoke_key_cmd(label: str) -> None:
    """Revoke a deploy key."""
    if revoke_deploy_key(label):
        success(f"Deploy key '{label}' revoked")
    else:
        error(f"No deploy key with label '{label}' found")
        raise SystemExit(1)


@ci.command()
@click.argument("app_name")
def setup(app_name: str) -> None:
    """Output a GitHub Actions workflow for deploying an app."""
    init_db()
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == app_name).first()
        if not app_obj:
            error(f"App '{app_name}' not found")
            raise SystemExit(1)

    workflow = f"""name: Deploy {app_name}

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Trigger deploy
        run: |
          curl -sf -X POST ${{{{ secrets.INFRAKT_URL }}}}/api/deploy \\
            -H "X-API-Key: ${{{{ secrets.INFRAKT_DEPLOY_KEY }}}}" \\
            -H "Content-Type: application/json" \\
            -d '{{"app_name": "{app_name}"}}'
"""
    info("Add these GitHub repository secrets:")
    info("  INFRAKT_URL      — Your infrakt API URL (e.g. https://infrakt.example.com)")
    info("  INFRAKT_DEPLOY_KEY — Generated with 'infrakt ci generate-key'")
    info("")
    info("Workflow file (.github/workflows/deploy.yml):")
    click.echo(workflow)
