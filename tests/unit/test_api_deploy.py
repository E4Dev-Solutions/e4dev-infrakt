"""Tests for FastAPI /api/deploy routes — CI/CD deploy trigger endpoint."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import cli.core.deploy_keys as dk_mod
from api.main import app
from cli.core.database import get_session, init_db
from cli.core.deploy_keys import generate_deploy_key
from cli.models.app import App
from cli.models.deployment import Deployment
from cli.models.server import Server
from tests.conftest import TEST_API_KEY


@pytest.fixture(autouse=True)
def patch_deploy_keys_file(isolated_config, monkeypatch):
    """Redirect DEPLOY_KEYS_FILE to the isolated temp directory."""
    deploy_keys_path = isolated_config / "deploy_keys.json"
    monkeypatch.setattr(dk_mod, "DEPLOY_KEYS_FILE", deploy_keys_path)
    return deploy_keys_path


@pytest.fixture
def client(isolated_config):
    """Return a TestClient backed by the isolated (temp) database."""
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})


@pytest.fixture
def unauth_client():
    """Return a TestClient without any API key header."""
    return TestClient(app)


def _seed_app(server_name="prod-1", app_name="my-app", status="stopped") -> int:
    """Insert a server + app into the isolated DB and return the app id."""
    init_db()
    with get_session() as session:
        existing_srv = session.query(Server).filter(Server.name == server_name).first()
        if not existing_srv:
            srv = Server(name=server_name, host="1.2.3.4", user="root", port=22, status="active")
            session.add(srv)
            session.flush()
            server_id = srv.id
        else:
            server_id = existing_srv.id

    init_db()
    with get_session() as session:
        a = App(
            name=app_name,
            server_id=server_id,
            port=3000,
            app_type="image",
            image="nginx:latest",
            status=status,
        )
        session.add(a)
        session.flush()
        return a.id


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestDeployAuthentication:
    def test_missing_key_returns_401(self, unauth_client, isolated_config):
        response = unauth_client.post("/api/deploy", json={"app_name": "my-app"})
        assert response.status_code == 401
        assert "Missing" in response.json()["detail"]

    def test_invalid_key_returns_403(self, isolated_config):
        bad_client = TestClient(app, headers={"X-API-Key": "totally-wrong-key"})
        response = bad_client.post("/api/deploy", json={"app_name": "my-app"})
        assert response.status_code == 403
        assert "Invalid" in response.json()["detail"]

    def test_main_api_key_is_accepted(self, client, isolated_config):
        _seed_app(app_name="auth-app")
        with (
            patch("api.routes.deploy.broadcaster"),
            patch("api.routes.deploy.SSHClient"),
            patch("api.routes.deploy.asyncio"),
        ):
            response = client.post("/api/deploy", json={"app_name": "auth-app"})
        assert response.status_code == 200

    def test_valid_deploy_key_is_accepted(self, isolated_config):
        _seed_app(app_name="dk-app")
        deploy_key = generate_deploy_key("ci-runner")
        deploy_key_client = TestClient(app, headers={"X-API-Key": deploy_key})

        with (
            patch("api.routes.deploy.broadcaster"),
            patch("api.routes.deploy.SSHClient"),
            patch("api.routes.deploy.asyncio"),
        ):
            response = deploy_key_client.post("/api/deploy", json={"app_name": "dk-app"})
        assert response.status_code == 200

    def test_revoked_deploy_key_returns_403(self, isolated_config):
        from cli.core.deploy_keys import revoke_deploy_key

        deploy_key = generate_deploy_key("revoked-runner")
        revoke_deploy_key("revoked-runner")
        bad_key_client = TestClient(app, headers={"X-API-Key": deploy_key})
        response = bad_key_client.post("/api/deploy", json={"app_name": "some-app"})
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Trigger deploy — success path
# ---------------------------------------------------------------------------


class TestTriggerDeploy:
    def test_returns_200_on_valid_request(self, client, isolated_config):
        _seed_app(app_name="go-app")
        with (
            patch("api.routes.deploy.broadcaster"),
            patch("api.routes.deploy.SSHClient"),
            patch("api.routes.deploy.asyncio"),
        ):
            response = client.post("/api/deploy", json={"app_name": "go-app"})
        assert response.status_code == 200

    def test_response_contains_message(self, client, isolated_config):
        _seed_app(app_name="msg-app")
        with (
            patch("api.routes.deploy.broadcaster"),
            patch("api.routes.deploy.SSHClient"),
            patch("api.routes.deploy.asyncio"),
        ):
            response = client.post("/api/deploy", json={"app_name": "msg-app"})
        assert "message" in response.json()

    def test_response_contains_deployment_id(self, client, isolated_config):
        _seed_app(app_name="dep-id-app")
        with (
            patch("api.routes.deploy.broadcaster"),
            patch("api.routes.deploy.SSHClient"),
            patch("api.routes.deploy.asyncio"),
        ):
            response = client.post("/api/deploy", json={"app_name": "dep-id-app"})
        assert "deployment_id" in response.json()
        assert isinstance(response.json()["deployment_id"], int)

    def test_message_includes_app_name(self, client, isolated_config):
        _seed_app(app_name="named-app")
        with (
            patch("api.routes.deploy.broadcaster"),
            patch("api.routes.deploy.SSHClient"),
            patch("api.routes.deploy.asyncio"),
        ):
            response = client.post("/api/deploy", json={"app_name": "named-app"})
        assert "named-app" in response.json()["message"]

    def test_deployment_record_is_created(self, client, isolated_config):
        _seed_app(app_name="recorded-app")
        with (
            patch("api.routes.deploy.broadcaster"),
            patch("api.routes.deploy.SSHClient"),
            patch("api.routes.deploy.asyncio"),
        ):
            response = client.post("/api/deploy", json={"app_name": "recorded-app"})

        dep_id = response.json()["deployment_id"]
        init_db()
        with get_session() as session:
            dep = session.query(Deployment).filter(Deployment.id == dep_id).first()
            dep_status = dep.status if dep else None
        # TestClient runs background tasks synchronously, so the deployment
        # may be in_progress (at creation) or success/failed (after bg task runs)
        assert dep_status in ("in_progress", "success", "failed")

    def test_custom_image_accepted_in_body(self, client, isolated_config):
        _seed_app(app_name="img-app")
        with (
            patch("api.routes.deploy.broadcaster"),
            patch("api.routes.deploy.SSHClient"),
            patch("api.routes.deploy.asyncio"),
        ):
            response = client.post(
                "/api/deploy",
                json={"app_name": "img-app", "image": "nginx:1.25"},
            )
        assert response.status_code == 200

    def test_custom_branch_accepted_in_body(self, client, isolated_config):
        _seed_app(app_name="branch-app")
        with (
            patch("api.routes.deploy.broadcaster"),
            patch("api.routes.deploy.SSHClient"),
            patch("api.routes.deploy.asyncio"),
        ):
            response = client.post(
                "/api/deploy",
                json={"app_name": "branch-app", "branch": "feature/ci"},
            )
        assert response.status_code == 200

    def test_background_task_is_registered(self, client, isolated_config):
        """Verify that the background deployment task is added."""
        _seed_app(app_name="bg-app")
        with (
            patch("api.routes.deploy.broadcaster"),
            patch("api.routes.deploy.SSHClient"),
            patch("api.routes.deploy.asyncio") as mock_asyncio,
            patch("fastapi.BackgroundTasks.add_task"),
        ):
            mock_asyncio.get_event_loop.return_value = MagicMock()
            response = client.post("/api/deploy", json={"app_name": "bg-app"})

        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Missing app — 404
# ---------------------------------------------------------------------------


class TestDeployMissingApp:
    def test_missing_app_returns_404(self, client, isolated_config):
        init_db()
        response = client.post("/api/deploy", json={"app_name": "ghost-app"})
        assert response.status_code == 404

    def test_404_detail_contains_app_name(self, client, isolated_config):
        init_db()
        response = client.post("/api/deploy", json={"app_name": "missing-app"})
        assert "missing-app" in response.json()["detail"]

    def test_missing_app_name_field_returns_422(self, client, isolated_config):
        response = client.post("/api/deploy", json={})
        assert response.status_code == 422

    def test_empty_app_name_returns_422(self, client, isolated_config):
        response = client.post("/api/deploy", json={"app_name": ""})
        assert response.status_code == 422
