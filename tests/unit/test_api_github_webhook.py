"""Tests for the GitHub push webhook receiver."""

import hashlib
import hmac
import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from api.main import app
from cli.core.database import get_session, init_db
from cli.models.app import App
from cli.models.server import Server

client = TestClient(app)


def _create_app_with_webhook(session, secret="test-secret"):
    srv = Server(name="srv1", host="1.2.3.4", user="root", port=22, status="active")
    session.add(srv)
    session.flush()
    a = App(
        name="my-app",
        server_id=srv.id,
        port=3000,
        status="running",
        app_type="git",
        git_repo="https://github.com/org/repo.git",
        branch="main",
        webhook_secret=secret,
        auto_deploy=True,
    )
    session.add(a)
    session.flush()
    return a


def _sign(payload_bytes: bytes, secret: str) -> str:
    sig = hmac.new(secret.encode(), payload_bytes, hashlib.sha256).hexdigest()
    return f"sha256={sig}"


def test_webhook_ping():
    resp = client.post(
        "/api/deploy/github-webhook",
        json={},
        headers={"X-GitHub-Event": "ping"},
    )
    assert resp.status_code == 200
    assert resp.json()["message"] == "pong"


def test_webhook_ignores_non_push_event():
    resp = client.post(
        "/api/deploy/github-webhook",
        json={},
        headers={"X-GitHub-Event": "issues"},
    )
    assert resp.status_code == 200
    assert "ignored" in resp.json()["message"].lower()


def test_webhook_rejects_missing_signature():
    init_db()
    resp = client.post(
        "/api/deploy/github-webhook",
        json={"ref": "refs/heads/main"},
        headers={"X-GitHub-Event": "push"},
    )
    assert resp.status_code == 400


@patch("api.routes.github_webhook._trigger_deploy")
def test_webhook_accepts_valid_push(mock_trigger):
    mock_trigger.return_value = None
    init_db()
    with get_session() as session:
        _create_app_with_webhook(session, secret="mysecret")

    payload = {
        "ref": "refs/heads/main",
        "repository": {"clone_url": "https://github.com/org/repo.git"},
    }
    # Use content= to control exact bytes for HMAC signing
    body_bytes = json.dumps(payload).encode()
    sig = _sign(body_bytes, "mysecret")
    resp = client.post(
        "/api/deploy/github-webhook",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 200
    assert "triggered" in resp.json()["message"].lower()
    mock_trigger.assert_called_once()


def test_webhook_rejects_bad_signature():
    init_db()
    with get_session() as session:
        _create_app_with_webhook(session, secret="mysecret")

    payload = {
        "ref": "refs/heads/main",
        "repository": {"clone_url": "https://github.com/org/repo.git"},
    }
    body_bytes = json.dumps(payload).encode()
    sig = _sign(body_bytes, "wrong-secret")
    resp = client.post(
        "/api/deploy/github-webhook",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 200
    # No app matched because signature didn't match, falls through
    assert "no matching" in resp.json()["message"].lower()


def test_webhook_ignores_wrong_branch():
    init_db()
    with get_session() as session:
        _create_app_with_webhook(session, secret="mysecret")

    payload = {
        "ref": "refs/heads/develop",
        "repository": {"clone_url": "https://github.com/org/repo.git"},
    }
    body_bytes = json.dumps(payload).encode()
    sig = _sign(body_bytes, "mysecret")
    resp = client.post(
        "/api/deploy/github-webhook",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 200
    assert "no matching" in resp.json()["message"].lower()


def test_webhook_respects_auto_deploy_off():
    init_db()
    with get_session() as session:
        a = _create_app_with_webhook(session, secret="mysecret")
        a.auto_deploy = False

    payload = {
        "ref": "refs/heads/main",
        "repository": {"clone_url": "https://github.com/org/repo.git"},
    }
    body_bytes = json.dumps(payload).encode()
    sig = _sign(body_bytes, "mysecret")
    resp = client.post(
        "/api/deploy/github-webhook",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 200
    assert "disabled" in resp.json()["message"].lower()


def test_webhook_no_matching_repo():
    init_db()
    with get_session() as session:
        _create_app_with_webhook(session, secret="mysecret")

    payload = {
        "ref": "refs/heads/main",
        "repository": {"clone_url": "https://github.com/other/repo.git"},
    }
    body_bytes = json.dumps(payload).encode()
    sig = _sign(body_bytes, "mysecret")
    resp = client.post(
        "/api/deploy/github-webhook",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 200
    assert "no matching" in resp.json()["message"].lower()


def test_webhook_missing_ref():
    init_db()
    payload = {"repository": {"clone_url": "https://github.com/org/repo.git"}}
    body_bytes = json.dumps(payload).encode()
    sig = _sign(body_bytes, "any")
    resp = client.post(
        "/api/deploy/github-webhook",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 200
    assert "missing" in resp.json()["message"].lower()


def test_webhook_app_without_secret_skipped():
    """An app with no webhook_secret should be skipped."""
    init_db()
    with get_session() as session:
        _create_app_with_webhook(session, secret=None)

    payload = {
        "ref": "refs/heads/main",
        "repository": {"clone_url": "https://github.com/org/repo.git"},
    }
    body_bytes = json.dumps(payload).encode()
    sig = _sign(body_bytes, "any-secret")
    resp = client.post(
        "/api/deploy/github-webhook",
        content=body_bytes,
        headers={
            "Content-Type": "application/json",
            "X-GitHub-Event": "push",
            "X-Hub-Signature-256": sig,
        },
    )
    assert resp.status_code == 200
    assert "no matching" in resp.json()["message"].lower()
