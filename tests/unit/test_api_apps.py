"""Tests for FastAPI /api/apps routes."""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from cli.core.database import get_session, init_db
from cli.models.app import App
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
