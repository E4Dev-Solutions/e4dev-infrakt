"""Tests for FastAPI /api/apps routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from cli.core.database import get_session, init_db
from cli.models.app import App
from cli.models.deployment import Deployment
from cli.models.server import Server
from tests.conftest import TEST_API_KEY


@pytest.fixture
def client(isolated_config):
    """Return a TestClient backed by the isolated (temp) database."""
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})


def _seed_server(name="srv-1", host="1.2.3.4", user="root"):
    """Insert a server directly into the isolated DB and return its name."""
    init_db()
    with get_session() as session:
        srv = Server(name=name, host=host, user=user, port=22, status="active")
        session.add(srv)
    return name


def _seed_app(server_name="srv-1", app_name="my-app", status="stopped", domain=None):
    """Insert a server + app into the isolated DB and return the app name."""
    _seed_server(server_name)
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        a = App(
            name=app_name,
            server_id=srv.id,
            port=3000,
            app_type="git",
            status=status,
            domain=domain,
        )
        session.add(a)
    return app_name


# ---------------------------------------------------------------------------
# GET /api/apps
# ---------------------------------------------------------------------------


class TestListApps:
    def test_returns_empty_list_when_no_apps(self, client, isolated_config):
        response = client.get("/api/apps")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_created_apps(self, client, isolated_config):
        _seed_app("srv-1", "hello-api")
        response = client.get("/api/apps")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "hello-api"

    def test_response_includes_server_name(self, client, isolated_config):
        _seed_app("my-server", "svc")
        response = client.get("/api/apps")
        assert response.json()[0]["server_name"] == "my-server"

    def test_filters_apps_by_server_query_param(self, client, isolated_config):
        _seed_app("prod", "prod-app")
        _seed_server("staging", host="2.2.2.2")
        init_db()
        with get_session() as session:
            staging = session.query(Server).filter(Server.name == "staging").first()
            session.add(App(name="stage-app", server_id=staging.id, port=3000, app_type="git"))

        response = client.get("/api/apps?server=prod")
        names = [a["name"] for a in response.json()]
        assert "prod-app" in names
        assert "stage-app" not in names

    def test_excludes_database_type_apps(self, client, isolated_config):
        # Apps with app_type starting with "db:" are internal databases and must be excluded
        _seed_server("srv-1")
        init_db()
        with get_session() as session:
            srv = session.query(Server).filter(Server.name == "srv-1").first()
            session.add(App(name="pg-db", server_id=srv.id, port=5432, app_type="db:postgres"))
            session.add(App(name="web-svc", server_id=srv.id, port=3000, app_type="git"))

        response = client.get("/api/apps")
        names = [a["name"] for a in response.json()]
        assert "web-svc" in names
        assert "pg-db" not in names

    def test_response_includes_expected_fields(self, client, isolated_config):
        _seed_app()
        data = client.get("/api/apps").json()[0]
        for field in ("id", "name", "server_id", "server_name", "port", "status", "app_type"):
            assert field in data


# ---------------------------------------------------------------------------
# POST /api/apps
# ---------------------------------------------------------------------------


class TestCreateApp:
    def test_creates_app_and_returns_201(self, client, isolated_config):
        _seed_server("prod")
        payload = {"name": "api-svc", "server_name": "prod", "port": 8080}
        response = client.post("/api/apps", json=payload)
        assert response.status_code == 201
        assert response.json()["name"] == "api-svc"

    def test_new_app_has_stopped_status(self, client, isolated_config):
        _seed_server("prod")
        response = client.post("/api/apps", json={"name": "idle-svc", "server_name": "prod"})
        assert response.status_code == 201
        assert response.json()["status"] == "stopped"

    def test_image_app_gets_image_type(self, client, isolated_config):
        _seed_server("prod")
        payload = {"name": "img-svc", "server_name": "prod", "image": "redis:7"}
        response = client.post("/api/apps", json=payload)
        assert response.status_code == 201
        assert response.json()["app_type"] == "image"

    def test_git_app_gets_git_type(self, client, isolated_config):
        _seed_server("prod")
        payload = {
            "name": "git-svc",
            "server_name": "prod",
            "git_repo": "https://github.com/org/repo.git",
        }
        response = client.post("/api/apps", json=payload)
        assert response.status_code == 201
        assert response.json()["app_type"] == "git"

    def test_returns_400_on_duplicate_app_name_on_same_server(self, client, isolated_config):
        _seed_server("prod")
        payload = {"name": "dup-app", "server_name": "prod"}
        client.post("/api/apps", json=payload)
        response = client.post("/api/apps", json=payload)
        assert response.status_code == 400
        assert "dup-app" in response.json()["detail"]

    def test_returns_404_when_server_not_found(self, client, isolated_config):
        payload = {"name": "orphan", "server_name": "nonexistent"}
        response = client.post("/api/apps", json=payload)
        assert response.status_code == 404
        assert "nonexistent" in response.json()["detail"]

    def test_returns_422_when_name_is_missing(self, client, isolated_config):
        _seed_server("prod")
        response = client.post("/api/apps", json={"server_name": "prod"})
        assert response.status_code == 422

    def test_rejects_invalid_domain_format(self, client, isolated_config):
        _seed_server("prod")
        payload = {"name": "bad-domain", "server_name": "prod", "domain": "not a domain!!"}
        response = client.post("/api/apps", json=payload)
        assert response.status_code == 422

    def test_allows_same_app_name_on_different_servers(self, client, isolated_config):
        _seed_server("prod", host="1.1.1.1")
        _seed_server("staging", host="2.2.2.2")
        payload_prod = {"name": "shared-name", "server_name": "prod"}
        payload_staging = {"name": "shared-name", "server_name": "staging"}
        r1 = client.post("/api/apps", json=payload_prod)
        r2 = client.post("/api/apps", json=payload_staging)
        assert r1.status_code == 201
        assert r2.status_code == 201


# ---------------------------------------------------------------------------
# POST /api/apps/{name}/stop
# ---------------------------------------------------------------------------


class TestStopApp:
    def test_stop_returns_success_message(self, client, isolated_config):
        _seed_app("srv-1", "running-app", status="running")
        with patch("api.routes.apps.SSHClient") as mock_cls, patch("api.routes.apps.stop_app"):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            response = client.post("/api/apps/running-app/stop")

        assert response.status_code == 200
        assert "running-app" in response.json()["message"]

    def test_stop_updates_app_status_to_stopped_in_db(self, client, isolated_config):
        _seed_app("srv-1", "active-app", status="running")
        with patch("api.routes.apps.SSHClient") as mock_cls, patch("api.routes.apps.stop_app"):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            client.post("/api/apps/active-app/stop")

        init_db()
        with get_session() as session:
            a = session.query(App).filter(App.name == "active-app").first()
            status = a.status if a else None
        assert status == "stopped"

    def test_stop_returns_404_when_app_not_found(self, client, isolated_config):
        response = client.post("/api/apps/ghost-app/stop")
        assert response.status_code == 404
        assert "ghost-app" in response.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /api/apps/{name}
# ---------------------------------------------------------------------------


class TestDestroyApp:
    def test_destroy_removes_app_from_database(self, client, isolated_config):
        _seed_app("srv-1", "doom-app")
        with patch("api.routes.apps.SSHClient") as mock_cls, patch("api.routes.apps.destroy_app"):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            response = client.delete("/api/apps/doom-app")

        assert response.status_code == 200
        init_db()
        with get_session() as session:
            a = session.query(App).filter(App.name == "doom-app").first()
        assert a is None

    def test_destroy_returns_success_message(self, client, isolated_config):
        _seed_app("srv-1", "bye-app")
        with patch("api.routes.apps.SSHClient") as mock_cls, patch("api.routes.apps.destroy_app"):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            response = client.delete("/api/apps/bye-app")

        assert "bye-app" in response.json()["message"]

    def test_destroy_also_calls_remove_domain_when_domain_set(self, client, isolated_config):
        _seed_app("srv-1", "domain-app", domain="api.example.com")
        with (
            patch("api.routes.apps.SSHClient") as mock_cls,
            patch("api.routes.apps.destroy_app"),
            patch("api.routes.apps.remove_domain") as mock_remove,
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            client.delete("/api/apps/domain-app")

        mock_remove.assert_called_once_with(mock_ssh, "api.example.com")

    def test_destroy_returns_404_when_app_not_found(self, client, isolated_config):
        response = client.delete("/api/apps/ghost-app")
        assert response.status_code == 404
        assert "ghost-app" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/apps/{name}/deployments/{dep_id}/logs/stream
# ---------------------------------------------------------------------------


class TestStreamDeploymentLogs:
    def test_returns_404_for_unknown_app(self, client, isolated_config):
        response = client.get("/api/apps/ghost/deployments/1/logs/stream")
        assert response.status_code == 404

    def test_returns_404_for_unknown_deployment(self, client, isolated_config):
        _seed_app("srv-1", "my-app")
        response = client.get("/api/apps/my-app/deployments/999/logs/stream")
        assert response.status_code == 404

    def test_streams_stored_log_for_finished_deployment(self, client, isolated_config):
        _seed_app("srv-1", "my-app")
        init_db()
        with get_session() as session:
            app_obj = session.query(App).filter(App.name == "my-app").first()
            dep = Deployment(app_id=app_obj.id, status="success", log="line1\nline2")
            session.add(dep)
            session.flush()
            dep_id = dep.id

        response = client.get(f"/api/apps/my-app/deployments/{dep_id}/logs/stream")
        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = response.text
        assert '"line1"' in body
        assert '"line2"' in body
        assert '"done": true' in body


# ---------------------------------------------------------------------------
# GET /api/apps/{name}/health
# ---------------------------------------------------------------------------


class TestAppHealth:
    def test_returns_health_data_for_running_app(self, client, isolated_config):
        _seed_app("srv-1", "my-app", status="running")
        with (
            patch("api.routes.apps.SSHClient") as mock_cls,
            patch("api.routes.apps.get_container_health") as mock_health,
            patch("api.routes.apps.reconcile_app_status") as mock_reconcile,
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            mock_health.return_value = [
                {
                    "name": "infrakt-my-app",
                    "state": "running",
                    "status": "Up 1 hour",
                    "image": "nginx:latest",
                    "health": "",
                }
            ]
            mock_reconcile.return_value = "running"
            response = client.get("/api/apps/my-app/health")

        assert response.status_code == 200
        data = response.json()
        assert data["actual_status"] == "running"
        assert data["status_mismatch"] is False
        assert len(data["containers"]) == 1
        assert data["containers"][0]["name"] == "infrakt-my-app"

    def test_reconciles_db_status_on_mismatch(self, client, isolated_config):
        _seed_app("srv-1", "my-app", status="running")
        with (
            patch("api.routes.apps.SSHClient") as mock_cls,
            patch("api.routes.apps.get_container_health") as mock_health,
            patch("api.routes.apps.reconcile_app_status") as mock_reconcile,
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            mock_health.return_value = []
            mock_reconcile.return_value = "stopped"
            response = client.get("/api/apps/my-app/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status_mismatch"] is True
        assert data["db_status"] == "running"
        assert data["actual_status"] == "stopped"

        # Verify DB was updated
        init_db()
        with get_session() as session:
            a = session.query(App).filter(App.name == "my-app").first()
            assert a.status == "stopped"

    def test_returns_404_for_unknown_app(self, client, isolated_config):
        response = client.get("/api/apps/ghost-app/health")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# POST /api/apps/{name}/rollback
# ---------------------------------------------------------------------------


def _seed_deployment(app_name="my-app", status="success", commit_hash=None, image_used=None):
    """Insert a deployment record for the given app."""
    init_db()
    with get_session() as session:
        a = session.query(App).filter(App.name == app_name).first()
        dep = Deployment(
            app_id=a.id,
            status=status,
            commit_hash=commit_hash,
            image_used=image_used,
            log="test log",
        )
        session.add(dep)
        session.flush()
        return dep.id


class TestRollback:
    def test_rollback_with_deployment_id(self, client, isolated_config):
        _seed_app("srv-1", "my-app", status="running")
        dep_id = _seed_deployment("my-app", status="success", image_used="nginx:1.24")
        _seed_deployment("my-app", status="success", image_used="nginx:1.25")

        with (
            patch("api.routes.apps.broadcaster"),
            patch("api.routes.apps.asyncio"),
            patch("api.routes.apps.SSHClient"),
            patch("api.routes.apps.deploy_app"),
        ):
            response = client.post(f"/api/apps/my-app/rollback?deployment_id={dep_id}")
        assert response.status_code == 200
        data = response.json()
        assert "deployment_id" in data
        assert data["deployment_id"] != dep_id

    def test_rollback_without_deployment_id_uses_second_success(self, client, isolated_config):
        _seed_app("srv-1", "my-app", status="running")
        _seed_deployment("my-app", status="success", image_used="nginx:1.24")
        _seed_deployment("my-app", status="success", image_used="nginx:1.25")

        with (
            patch("api.routes.apps.broadcaster"),
            patch("api.routes.apps.asyncio"),
            patch("api.routes.apps.SSHClient"),
            patch("api.routes.apps.deploy_app"),
        ):
            response = client.post("/api/apps/my-app/rollback")
        assert response.status_code == 200
        assert "deployment_id" in response.json()

    def test_rollback_returns_404_when_no_previous_deployment(self, client, isolated_config):
        _seed_app("srv-1", "my-app", status="running")
        _seed_deployment("my-app", status="success", image_used="nginx:1.25")

        response = client.post("/api/apps/my-app/rollback")
        assert response.status_code == 404
        assert "No previous" in response.json()["detail"]


# ---------------------------------------------------------------------------
# GET /api/apps/{name}/logs/stream
# ---------------------------------------------------------------------------


class TestStreamAppLogs:
    def test_returns_404_for_unknown_app(self, client, isolated_config):
        response = client.get("/api/apps/ghost-app/logs/stream")
        assert response.status_code == 404

    def test_returns_sse_content_type(self, client, isolated_config):
        _seed_app("srv-1", "my-app", status="running")
        with (
            patch("api.routes.apps.SSHClient") as mock_cls,
            patch("api.routes.apps.stream_logs") as mock_stream,
        ):
            mock_ssh = MagicMock()
            mock_cls.from_server.return_value = mock_ssh
            mock_stream.return_value = iter(["log line 1", "log line 2"])
            response = client.get("/api/apps/my-app/logs/stream?lines=50")

        assert response.status_code == 200
        assert "text/event-stream" in response.headers["content-type"]
        body = response.text
        assert '"log line 1"' in body
        assert '"log line 2"' in body


# ---------------------------------------------------------------------------
# POST /api/apps/{name}/deploy — GitHub webhook auto-creation
# ---------------------------------------------------------------------------


def _seed_github_app(server_name="srv-1", app_name="gh-app"):
    """Insert a server + GitHub app (with git_repo) into the isolated DB."""
    _seed_server(server_name)
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        a = App(
            name=app_name,
            server_id=srv.id,
            port=3000,
            app_type="git",
            status="stopped",
            git_repo="https://github.com/myorg/myrepo.git",
            branch="main",
        )
        session.add(a)
    return app_name


class TestDeployCreatesGitHubWebhook:
    @patch("api.routes.apps.create_repo_webhook")
    @patch("api.routes.apps.get_github_token")
    def test_deploy_creates_github_webhook(self, mock_get_token, mock_create_hook, client, isolated_config):
        """When deploying a GitHub app with PAT connected, a webhook is auto-created."""
        from cli.core.deployer import DeployResult

        mock_get_token.return_value = "ghp_test"
        mock_create_hook.return_value = 12345

        _seed_github_app("srv-1", "gh-app")

        with (
            patch("api.routes.apps.broadcaster"),
            patch("api.routes.apps.asyncio") as mock_asyncio,
            patch("api.routes.apps.SSHClient") as mock_ssh_cls,
            patch("api.routes.apps.deploy_app") as mock_deploy,
            patch("api.routes.apps.env_content_for_app", return_value=""),
            patch("api.routes.apps.add_domain"),
            patch("api.routes.apps.fire_webhooks"),
        ):
            mock_asyncio.get_running_loop.return_value = MagicMock()
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_ssh_cls.return_value = mock_ssh
            mock_deploy.return_value = DeployResult(log="ok", commit_hash="abc123", image_used=None)

            response = client.post("/api/apps/gh-app/deploy")

        assert response.status_code == 200

        # Verify webhook was created
        mock_create_hook.assert_called_once()
        call_args = mock_create_hook.call_args
        assert call_args[0][0] == "ghp_test"  # token
        assert call_args[0][1] == "myorg"  # owner
        assert call_args[0][2] == "myrepo"  # repo
        assert "/api/deploy/github-webhook" in call_args[0][3]  # webhook_url
        assert call_args[0][4]  # secret is non-empty

        # Verify webhook_secret was set on the app in DB
        init_db()
        with get_session() as session:
            a = session.query(App).filter(App.name == "gh-app").first()
            assert a.webhook_secret is not None
            assert len(a.webhook_secret) > 0

    @patch("api.routes.apps.create_repo_webhook")
    @patch("api.routes.apps.get_github_token")
    def test_deploy_skips_webhook_if_no_github_token(self, mock_get_token, mock_create_hook, client, isolated_config):
        """When no GitHub PAT is connected, webhook creation is skipped."""
        from cli.core.deployer import DeployResult

        mock_get_token.return_value = None

        _seed_github_app("srv-1", "gh-app")

        with (
            patch("api.routes.apps.broadcaster"),
            patch("api.routes.apps.asyncio") as mock_asyncio,
            patch("api.routes.apps.SSHClient") as mock_ssh_cls,
            patch("api.routes.apps.deploy_app") as mock_deploy,
            patch("api.routes.apps.env_content_for_app", return_value=""),
            patch("api.routes.apps.add_domain"),
            patch("api.routes.apps.fire_webhooks"),
        ):
            mock_asyncio.get_running_loop.return_value = MagicMock()
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_ssh_cls.return_value = mock_ssh
            mock_deploy.return_value = DeployResult(log="ok", commit_hash="abc123", image_used=None)

            response = client.post("/api/apps/gh-app/deploy")

        assert response.status_code == 200
        mock_create_hook.assert_not_called()

    @patch("api.routes.apps.create_repo_webhook")
    @patch("api.routes.apps.get_github_token")
    def test_deploy_skips_webhook_if_already_set(self, mock_get_token, mock_create_hook, client, isolated_config):
        """When webhook_secret is already set, webhook creation is skipped."""
        from cli.core.deployer import DeployResult

        mock_get_token.return_value = "ghp_test"

        _seed_github_app("srv-1", "gh-app")
        # Pre-set webhook_secret
        init_db()
        with get_session() as session:
            a = session.query(App).filter(App.name == "gh-app").first()
            a.webhook_secret = "existing-secret"

        with (
            patch("api.routes.apps.broadcaster"),
            patch("api.routes.apps.asyncio") as mock_asyncio,
            patch("api.routes.apps.SSHClient") as mock_ssh_cls,
            patch("api.routes.apps.deploy_app") as mock_deploy,
            patch("api.routes.apps.env_content_for_app", return_value=""),
            patch("api.routes.apps.add_domain"),
            patch("api.routes.apps.fire_webhooks"),
        ):
            mock_asyncio.get_running_loop.return_value = MagicMock()
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_ssh_cls.return_value = mock_ssh
            mock_deploy.return_value = DeployResult(log="ok", commit_hash="abc123", image_used=None)

            response = client.post("/api/apps/gh-app/deploy")

        assert response.status_code == 200
        mock_create_hook.assert_not_called()
