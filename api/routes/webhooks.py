"""Webhook configuration management."""

from fastapi import APIRouter, HTTPException

from api.schemas import WebhookCreate, WebhookOut
from cli.core.database import get_session, init_db
from cli.core.webhook_sender import build_payload, deliver_webhook
from cli.models.webhook import Webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def _webhook_out(wh: Webhook) -> WebhookOut:
    return WebhookOut(
        id=wh.id,
        url=wh.url,
        events=wh.events.split(","),
        created_at=wh.created_at,
    )


@router.get("", response_model=list[WebhookOut])
def list_webhooks() -> list[WebhookOut]:
    """List all registered webhooks."""
    init_db()
    with get_session() as session:
        hooks = session.query(Webhook).order_by(Webhook.id).all()
        return [_webhook_out(h) for h in hooks]


@router.post("", response_model=WebhookOut, status_code=201)
def create_webhook(body: WebhookCreate) -> WebhookOut:
    """Register a new webhook."""
    init_db()
    with get_session() as session:
        hook = Webhook(
            url=body.url,
            events=",".join(body.events),
            secret=body.secret,
        )
        session.add(hook)
        session.flush()
        return _webhook_out(hook)


@router.delete("/{webhook_id}")
def delete_webhook(webhook_id: int) -> dict[str, str]:
    """Delete a webhook by ID."""
    init_db()
    with get_session() as session:
        hook = session.query(Webhook).filter(Webhook.id == webhook_id).first()
        if not hook:
            raise HTTPException(404, f"Webhook {webhook_id} not found")
        session.delete(hook)
    return {"message": f"Webhook {webhook_id} deleted"}


@router.post("/{webhook_id}/test")
def test_webhook(webhook_id: int) -> dict[str, str]:
    """Send a test ping payload to the webhook URL."""
    init_db()
    with get_session() as session:
        hook = session.query(Webhook).filter(Webhook.id == webhook_id).first()
        if not hook:
            raise HTTPException(404, f"Webhook {webhook_id} not found")
        url, secret = hook.url, hook.secret

    payload = build_payload("ping", {"message": "Test webhook from infrakt"})
    deliver_webhook(url, secret, payload)
    return {"message": "Test ping sent"}
