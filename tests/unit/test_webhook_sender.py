"""Tests for cli.core.webhook_sender.

Covers payload building, HTTP delivery (including HMAC signing), error
suppression, and event-filtered fan-out via the database.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
from unittest.mock import patch

from cli.core.database import get_session, init_db
from cli.core.webhook_sender import build_payload, deliver_webhook, fire_webhooks
from cli.models.webhook import Webhook

# ---------------------------------------------------------------------------
# build_payload
# ---------------------------------------------------------------------------


class TestBuildPayload:
    def test_build_payload_includes_event_and_timestamp(self, isolated_config):
        """Returned dict must carry the event name, an ISO timestamp, and the data."""
        payload = build_payload("deploy.success", {"app": "myapp"})

        assert payload["event"] == "deploy.success"
        assert "timestamp" in payload
        # ISO 8601 timestamps contain 'T'
        assert "T" in payload["timestamp"]
        assert payload["data"] == {"app": "myapp"}

    def test_build_payload_timestamp_changes_between_calls(self, isolated_config):
        """Each call should produce a fresh timestamp (not a module-level constant)."""
        import time

        p1 = build_payload("deploy.success", {})
        time.sleep(0.01)
        p2 = build_payload("deploy.success", {})
        # Timestamps are distinct strings — they are not cached
        assert p1["timestamp"] != p2["timestamp"]

    def test_build_payload_passes_arbitrary_data(self, isolated_config):
        """The data field is echoed back unchanged."""
        data = {"server": "prod-1", "status": "ok", "nested": {"k": "v"}}
        payload = build_payload("backup.complete", data)
        assert payload["data"] == data


# ---------------------------------------------------------------------------
# deliver_webhook
# ---------------------------------------------------------------------------


class TestDeliverWebhook:
    def test_deliver_webhook_sends_post(self, isolated_config):
        """urlopen is called with a POST Request to the supplied URL."""
        payload = {"event": "deploy.success", "timestamp": "2026-01-01T00:00:00+00:00", "data": {}}

        with patch("urllib.request.urlopen") as mock_open:
            deliver_webhook("https://example.com/hook", None, payload)

        assert mock_open.called
        req: urllib.request.Request = mock_open.call_args[0][0]
        assert req.full_url == "https://example.com/hook"
        assert req.method == "POST"

    def test_deliver_webhook_sends_correct_json_body(self, isolated_config):
        """The request body is the JSON-serialised payload."""
        payload = {"event": "deploy.failure", "timestamp": "2026-01-01T00:00:00+00:00", "data": {}}

        with patch("urllib.request.urlopen") as mock_open:
            deliver_webhook("https://hooks.example.com/recv", None, payload)
            req: urllib.request.Request = mock_open.call_args[0][0]

        assert json.loads(req.data) == payload

    def test_deliver_webhook_adds_hmac_when_secret(self, isolated_config):
        """X-Webhook-Signature header is present and correct when a secret is given."""
        payload = {"event": "deploy.success", "timestamp": "2026-01-01T00:00:00+00:00", "data": {}}
        secret = "my-signing-secret"

        with patch("urllib.request.urlopen") as mock_open:
            deliver_webhook("https://example.com/hook", secret, payload)

        req: urllib.request.Request = mock_open.call_args[0][0]
        # urllib title-cases header names: "X-Webhook-Signature" → "X-webhook-signature"
        assert "X-webhook-signature" in req.headers

        # Recompute the expected signature to verify it matches
        body = json.dumps(payload).encode()
        expected_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
        assert req.headers["X-webhook-signature"] == f"sha256={expected_sig}"

    def test_deliver_webhook_no_signature_when_no_secret(self, isolated_config):
        """X-Webhook-Signature header must be absent when secret is None."""
        payload = {"event": "deploy.success", "timestamp": "2026-01-01T00:00:00+00:00", "data": {}}

        with patch("urllib.request.urlopen") as mock_open:
            deliver_webhook("https://example.com/hook", None, payload)

        req: urllib.request.Request = mock_open.call_args[0][0]
        # Header names are title-cased by urllib; check both casings
        header_keys_lower = {k.lower() for k in req.headers}
        assert "x-webhook-signature" not in header_keys_lower

    def test_deliver_webhook_swallows_url_error(self, isolated_config):
        """URLError from urlopen must be caught — deliver_webhook never raises."""
        payload = {"event": "deploy.success", "timestamp": "2026-01-01T00:00:00+00:00", "data": {}}

        with patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("connection refused"),
        ):
            # Must not raise
            deliver_webhook("https://dead-host.example.com/hook", None, payload)

    def test_deliver_webhook_swallows_os_error(self, isolated_config):
        """OSError (e.g. network unreachable) must also be swallowed."""
        payload = {"event": "backup.complete", "timestamp": "2026-01-01T00:00:00+00:00", "data": {}}

        with patch("urllib.request.urlopen", side_effect=OSError("network unreachable")):
            deliver_webhook("https://example.com/hook", None, payload)

    def test_deliver_webhook_passes_timeout_to_urlopen(self, isolated_config):
        """The timeout keyword argument must be forwarded to urlopen."""
        payload = {"event": "deploy.success", "timestamp": "t", "data": {}}

        with patch("urllib.request.urlopen") as mock_open:
            deliver_webhook("https://example.com/hook", None, payload, timeout=5)

        _, kwargs = mock_open.call_args
        assert kwargs.get("timeout") == 5

    def test_deliver_webhook_sets_content_type_header(self, isolated_config):
        """Content-Type must be application/json."""
        payload = {"event": "deploy.success", "timestamp": "t", "data": {}}

        with patch("urllib.request.urlopen") as mock_open:
            deliver_webhook("https://example.com/hook", None, payload)

        req: urllib.request.Request = mock_open.call_args[0][0]
        assert req.headers.get("Content-type") == "application/json"


# ---------------------------------------------------------------------------
# fire_webhooks
# ---------------------------------------------------------------------------


class TestFireWebhooks:
    def _seed_webhook(self, url: str, events: str, secret: str | None = None) -> None:
        """Insert a Webhook row directly into the isolated DB."""
        init_db()
        with get_session() as session:
            session.add(Webhook(url=url, events=events, secret=secret))

    def test_fire_webhooks_filters_by_event(self, isolated_config):
        """Only webhooks whose events field contains the fired event are delivered."""
        self._seed_webhook("https://match.example.com/hook", "deploy.success")
        self._seed_webhook("https://nomatch.example.com/hook", "backup.complete")

        with patch("cli.core.webhook_sender.deliver_webhook") as mock_deliver:
            fire_webhooks("deploy.success", {"app": "myapp"})

        called_urls = [call_args[0][0] for call_args in mock_deliver.call_args_list]
        assert "https://match.example.com/hook" in called_urls
        assert "https://nomatch.example.com/hook" not in called_urls

    def test_fire_webhooks_delivers_to_all_matching_hooks(self, isolated_config):
        """All webhooks subscribed to the event are invoked, not just the first."""
        self._seed_webhook("https://hook1.example.com/a", "deploy.success")
        self._seed_webhook("https://hook2.example.com/b", "deploy.success")
        self._seed_webhook("https://hook3.example.com/c", "deploy.failure")

        with patch("cli.core.webhook_sender.deliver_webhook") as mock_deliver:
            fire_webhooks("deploy.success", {})

        assert mock_deliver.call_count == 2

    def test_fire_webhooks_passes_secret_to_deliver(self, isolated_config):
        """The webhook's secret value is forwarded to deliver_webhook."""
        self._seed_webhook("https://signed.example.com/hook", "deploy.success", secret="s3cr3t")

        with patch("cli.core.webhook_sender.deliver_webhook") as mock_deliver:
            fire_webhooks("deploy.success", {})

        _, secret, _ = mock_deliver.call_args[0]
        assert secret == "s3cr3t"

    def test_fire_webhooks_with_no_matching_hooks_does_nothing(self, isolated_config):
        """fire_webhooks on an event with zero subscribers must not call deliver_webhook."""
        self._seed_webhook("https://other.example.com/hook", "backup.complete")

        with patch("cli.core.webhook_sender.deliver_webhook") as mock_deliver:
            fire_webhooks("deploy.failure", {})

        mock_deliver.assert_not_called()

    def test_fire_webhooks_with_empty_db_does_nothing(self, isolated_config):
        """fire_webhooks on an empty database must not call deliver_webhook."""
        init_db()

        with patch("cli.core.webhook_sender.deliver_webhook") as mock_deliver:
            fire_webhooks("deploy.success", {})

        mock_deliver.assert_not_called()

    def test_fire_webhooks_payload_contains_correct_event(self, isolated_config):
        """The payload passed to deliver_webhook has the correct event field."""
        self._seed_webhook("https://check.example.com/hook", "deploy.success")

        with patch("cli.core.webhook_sender.deliver_webhook") as mock_deliver:
            fire_webhooks("deploy.success", {"app": "testapp"})

        _url, _secret, payload = mock_deliver.call_args[0]
        assert payload["event"] == "deploy.success"
        assert payload["data"] == {"app": "testapp"}

    def test_fire_webhooks_handles_multi_event_webhook(self, isolated_config):
        """A webhook with a comma-separated events list matches any listed event."""
        self._seed_webhook(
            "https://multi.example.com/hook",
            "deploy.success,deploy.failure",
        )

        with patch("cli.core.webhook_sender.deliver_webhook") as mock_deliver:
            fire_webhooks("deploy.failure", {})

        assert mock_deliver.call_count == 1
