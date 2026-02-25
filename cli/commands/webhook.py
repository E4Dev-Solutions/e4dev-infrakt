"""Manage notification webhooks."""

import click

from cli.core.console import error, info, print_table, success
from cli.core.database import get_session, init_db
from cli.models.webhook import Webhook

VALID_EVENTS = ["deploy.success", "deploy.failure", "backup.complete", "backup.restore"]


@click.group()
def webhook() -> None:
    """Manage notification webhooks."""


@webhook.command("add")
@click.option("--url", required=True, help="HTTPS webhook endpoint URL")
@click.option(
    "--events",
    required=True,
    help="Comma-separated events: deploy.success,deploy.failure,backup.complete,backup.restore",
)
@click.option("--secret", default=None, help="HMAC-SHA256 signing secret")
def add(url: str, events: str, secret: str | None) -> None:
    """Register a new webhook."""
    init_db()
    event_list = [e.strip() for e in events.split(",")]
    invalid = [e for e in event_list if e not in VALID_EVENTS]
    if invalid:
        error(f"Invalid events: {invalid}. Valid: {VALID_EVENTS}")
        raise SystemExit(1)
    if not url.startswith("https://"):
        error("URL must use HTTPS")
        raise SystemExit(1)
    with get_session() as session:
        hook = Webhook(url=url, events=",".join(event_list), secret=secret)
        session.add(hook)
        session.flush()
        wh_id = hook.id
    success(f"Webhook registered (id={wh_id})")


@webhook.command("list")
def list_webhooks() -> None:
    """List all registered webhooks."""
    init_db()
    with get_session() as session:
        hooks = session.query(Webhook).order_by(Webhook.id).all()
        if not hooks:
            info("No webhooks registered.")
            return
        rows = [(str(h.id), h.url, h.events, "yes" if h.secret else "no") for h in hooks]
    print_table("Webhooks", ["ID", "URL", "Events", "Secret"], rows)


@webhook.command("remove")
@click.argument("webhook_id", type=int)
def remove(webhook_id: int) -> None:
    """Remove a webhook by ID."""
    init_db()
    with get_session() as session:
        hook = session.query(Webhook).filter(Webhook.id == webhook_id).first()
        if not hook:
            error(f"Webhook {webhook_id} not found")
            raise SystemExit(1)
        session.delete(hook)
    success(f"Webhook {webhook_id} removed")
