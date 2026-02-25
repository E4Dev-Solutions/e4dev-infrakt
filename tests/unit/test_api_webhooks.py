"""Tests for FastAPI /api/webhooks routes.

Covers listing, creation (including validation), deletion, and test-ping
dispatch for the webhook management endpoints.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from cli.core.database import get_session, init_db
from cli.models.webhook import Webhook
from tests.conftest import TEST_API_KEY


@pytest.fixture
def client(isolated_config):
    """Return a TestClient backed by the isolated (temp) database."""
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})


def _seed_webhook(url: str = "https://example.com/hook", events: str = "deploy.success") -> int:
    """Insert a Webhook row into the isolated DB; returns its ID."""
    init_db()
    with get_session() as session:
        hook = Webhook(url=url, events=events)
        session.add(hook)
        session.flush()
        return hook.id


# ---------------------------------------------------------------------------
# GET /api/webhooks
# ---------------------------------------------------------------------------


class TestListWebhooks:
    def test_list_webhooks_empty(self, client, isolated_config):
        """GET /api/webhooks returns an empty list when no webhooks are registered."""
        init_db()
        response = client.get("/api/webhooks")
        assert response.status_code == 200
        assert response.json() == []

    def test_list_webhooks_returns_seeded_hook(self, client, isolated_config):
        """GET /api/webhooks returns the single registered webhook."""
        _seed_webhook("https://hook.example.com/recv", "deploy.success")
        response = client.get("/api/webhooks")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["url"] == "https://hook.example.com/recv"

    def test_list_webhooks_events_is_a_list(self, client, isolated_config):
        """The events field in the response is deserialized as a list, not a string."""
        _seed_webhook("https://example.com/hook", "deploy.success,deploy.failure")
        response = client.get("/api/webhooks")
        events = response.json()[0]["events"]
        assert isinstance(events, list)
        assert "deploy.success" in events
        assert "deploy.failure" in events

    def test_list_webhooks_response_includes_expected_fields(self, client, isolated_config):
        """Each webhook in the list includes id, url, events, and created_at."""
        _seed_webhook()
        hook = client.get("/api/webhooks").json()[0]
        for field in ("id", "url", "events", "created_at"):
            assert field in hook


# ---------------------------------------------------------------------------
# POST /api/webhooks
# ---------------------------------------------------------------------------


class TestCreateWebhook:
    def test_create_webhook(self, client, isolated_config):
        """POST /api/webhooks with a valid payload returns 201 and the new webhook."""
        payload = {
            "url": "https://hooks.example.com/incoming",
            "events": ["deploy.success"],
        }
        response = client.post("/api/webhooks", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["url"] == "https://hooks.example.com/incoming"
        assert isinstance(data["events"], list)
        assert "deploy.success" in data["events"]
        assert "id" in data

    def test_create_webhook_persists_to_db(self, client, isolated_config):
        """After creation the webhook is retrievable via GET /api/webhooks."""
        payload = {
            "url": "https://persist.example.com/hook",
            "events": ["backup.complete"],
        }
        client.post("/api/webhooks", json=payload)
        response = client.get("/api/webhooks")
        urls = [h["url"] for h in response.json()]
        assert "https://persist.example.com/hook" in urls

    def test_create_webhook_with_multiple_events(self, client, isolated_config):
        """Creating a webhook with multiple events stores all of them."""
        payload = {
            "url": "https://multi.example.com/hook",
            "events": ["deploy.success", "deploy.failure", "backup.complete"],
        }
        response = client.post("/api/webhooks", json=payload)
        assert response.status_code == 201
        events = response.json()["events"]
        assert set(events) == {"deploy.success", "deploy.failure", "backup.complete"}

    def test_create_webhook_with_secret(self, client, isolated_config):
        """A webhook created with a secret does not echo the secret in the response."""
        payload = {
            "url": "https://signed.example.com/hook",
            "events": ["deploy.success"],
            "secret": "my-hmac-secret",
        }
        response = client.post("/api/webhooks", json=payload)
        assert response.status_code == 201
        # WebhookOut schema does not include the secret field
        assert "secret" not in response.json()

    def test_create_webhook_validates_https(self, client, isolated_config):
        """POST with an http:// (non-HTTPS) URL is rejected with 422."""
        payload = {
            "url": "http://insecure.example.com/hook",
            "events": ["deploy.success"],
        }
        response = client.post("/api/webhooks", json=payload)
        assert response.status_code == 422

    def test_create_webhook_validates_events(self, client, isolated_config):
        """POST with an unrecognised event name is rejected with 422."""
        payload = {
            "url": "https://example.com/hook",
            "events": ["invalid.event"],
        }
        response = client.post("/api/webhooks", json=payload)
        assert response.status_code == 422

    def test_create_webhook_rejects_empty_events_list(self, client, isolated_config):
        """POST with an empty events list is rejected with 422."""
        payload = {
            "url": "https://example.com/hook",
            "events": [],
        }
        response = client.post("/api/webhooks", json=payload)
        assert response.status_code == 422

    def test_create_webhook_rejects_missing_url(self, client, isolated_config):
        """POST without a url field is rejected with 422."""
        response = client.post("/api/webhooks", json={"events": ["deploy.success"]})
        assert response.status_code == 422

    def test_create_webhook_rejects_missing_events(self, client, isolated_config):
        """POST without an events field is rejected with 422."""
        response = client.post("/api/webhooks", json={"url": "https://example.com/hook"})
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# DELETE /api/webhooks/{id}
# ---------------------------------------------------------------------------


class TestDeleteWebhook:
    def test_delete_webhook(self, client, isolated_config):
        """DELETE /api/webhooks/{id} returns 200 and a confirmation message."""
        hook_id = _seed_webhook()
        response = client.delete(f"/api/webhooks/{hook_id}")
        assert response.status_code == 200
        assert str(hook_id) in response.json()["message"]

    def test_delete_webhook_removes_from_db(self, client, isolated_config):
        """After deletion the webhook no longer appears in GET /api/webhooks."""
        hook_id = _seed_webhook("https://todelete.example.com/hook")
        client.delete(f"/api/webhooks/{hook_id}")
        remaining = client.get("/api/webhooks").json()
        ids = [h["id"] for h in remaining]
        assert hook_id not in ids

    def test_delete_webhook_not_found(self, client, isolated_config):
        """DELETE /api/webhooks/999 returns 404 when the ID does not exist."""
        init_db()
        response = client.delete("/api/webhooks/999")
        assert response.status_code == 404
        assert "999" in response.json()["detail"]

    def test_delete_webhook_leaves_other_hooks_intact(self, client, isolated_config):
        """Deleting one webhook must not affect other webhooks."""
        id_a = _seed_webhook("https://keep.example.com/hook")
        id_b = _seed_webhook("https://delete-me.example.com/hook")
        client.delete(f"/api/webhooks/{id_b}")
        remaining_ids = [h["id"] for h in client.get("/api/webhooks").json()]
        assert id_a in remaining_ids
        assert id_b not in remaining_ids


# ---------------------------------------------------------------------------
# POST /api/webhooks/{id}/test
# ---------------------------------------------------------------------------


class TestTestWebhook:
    def test_test_webhook_not_found(self, client, isolated_config):
        """POST /api/webhooks/999/test returns 404 when the webhook does not exist."""
        init_db()
        response = client.post("/api/webhooks/999/test")
        assert response.status_code == 404
        assert "999" in response.json()["detail"]

    def test_test_webhook_calls_deliver(self, client, isolated_config):
        """POST /api/webhooks/{id}/test dispatches a ping payload via deliver_webhook."""
        hook_id = _seed_webhook("https://ping.example.com/hook")

        with patch("api.routes.webhooks.deliver_webhook") as mock_deliver:
            response = client.post(f"/api/webhooks/{hook_id}/test")

        assert response.status_code == 200
        msg = response.json()["message"].lower()
        assert "ping" in msg or "sent" in msg
        mock_deliver.assert_called_once()
        # First positional arg to deliver_webhook must be the registered URL
        url_arg = mock_deliver.call_args[0][0]
        assert url_arg == "https://ping.example.com/hook"

    def test_test_webhook_ping_event_in_payload(self, client, isolated_config):
        """The test-ping payload must carry event='ping'."""
        hook_id = _seed_webhook()

        with patch("api.routes.webhooks.deliver_webhook") as mock_deliver:
            client.post(f"/api/webhooks/{hook_id}/test")

        _url, _secret, payload = mock_deliver.call_args[0]
        assert payload["event"] == "ping"

    def test_test_webhook_succeeds_even_when_delivery_swallows_error(self, client, isolated_config):
        """The test endpoint returns 200 even if deliver_webhook internally swallows an error."""
        hook_id = _seed_webhook()

        # deliver_webhook never raises by contract; simulate that here
        with patch("api.routes.webhooks.deliver_webhook", return_value=None):
            response = client.post(f"/api/webhooks/{hook_id}/test")

        assert response.status_code == 200
