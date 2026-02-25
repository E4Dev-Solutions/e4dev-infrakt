"""Fire-and-forget webhook delivery."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import urllib.error
import urllib.request
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

VALID_EVENTS = frozenset(
    [
        "deploy.success",
        "deploy.failure",
        "backup.complete",
        "backup.restore",
    ]
)


def build_payload(event: str, data: dict) -> dict:
    """Build a webhook payload with event type and timestamp."""
    return {
        "event": event,
        "timestamp": datetime.now(UTC).isoformat(),
        "data": data,
    }


def deliver_webhook(url: str, secret: str | None, payload: dict, timeout: int = 10) -> None:
    """HTTP POST the payload to url. Logs errors — never raises."""
    body = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "User-Agent": "infrakt-webhooks/0.1",
        },
    )
    if secret:
        sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        req.add_header("X-Webhook-Signature", f"sha256={sig}")
    try:
        urllib.request.urlopen(req, timeout=timeout)  # noqa: S310
    except (urllib.error.URLError, OSError) as exc:
        logger.warning("Webhook delivery to %s failed: %s", url, exc)


def fire_webhooks(event: str, data: dict) -> None:
    """Load matching webhooks from DB and fire each."""
    from cli.core.database import get_session
    from cli.models.webhook import Webhook

    payload = build_payload(event, data)
    with get_session() as session:
        hooks = session.query(Webhook).all()
        targets = [(h.url, h.secret) for h in hooks if event in h.events.split(",")]

    for url, secret in targets:
        deliver_webhook(url, secret, payload)
