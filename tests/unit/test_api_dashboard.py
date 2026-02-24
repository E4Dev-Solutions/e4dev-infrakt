"""Tests for FastAPI GET /api/dashboard route."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from cli.core.database import init_db, get_session
from cli.models.server import Server
from cli.models.app import App
from cli.models.deployment import Deployment
from tests.conftest import TEST_API_KEY


@pytest.fixture
def client(isolated_config):
    """Return a TestClient backed by the isolated (temp) database."""
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})


def _seed_server(name, host, status="inactive"):
    init_db()
    with get_session() as session:
        srv = Server(name=name, host=host, user="root", port=22, status=status)
        session.add(srv)
    return name


def _seed_app(server_name, app_name, status="stopped", app_type="git"):
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        a = App(name=app_name, server_id=srv.id, port=3000, app_type=app_type, status=status)
        session.add(a)
        session.flush()
        return a.id


# ---------------------------------------------------------------------------
# GET /api/dashboard
# ---------------------------------------------------------------------------

class TestDashboardStats:
    def test_returns_200_with_zero_counts_when_empty(self, client, isolated_config):
        response = client.get("/api/dashboard")
        assert response.status_code == 200
        data = response.json()
        assert data["total_servers"] == 0
        assert data["active_servers"] == 0
        assert data["total_apps"] == 0
        assert data["running_apps"] == 0
        assert data["total_databases"] == 0
        assert data["recent_deployments"] == []

    def test_response_includes_all_required_fields(self, client, isolated_config):
        response = client.get("/api/dashboard")
        data = response.json()
        for field in (
            "total_servers",
            "active_servers",
            "total_apps",
            "running_apps",
            "total_databases",
            "recent_deployments",
        ):
            assert field in data

    def test_total_servers_count_is_correct(self, client, isolated_config):
        _seed_server("s1", "1.1.1.1")
        _seed_server("s2", "2.2.2.2")
        _seed_server("s3", "3.3.3.3")
        response = client.get("/api/dashboard")
        assert response.json()["total_servers"] == 3

    def test_active_servers_count_excludes_inactive(self, client, isolated_config):
        _seed_server("active-1", "1.1.1.1", status="active")
        _seed_server("active-2", "2.2.2.2", status="active")
        _seed_server("inactive-1", "3.3.3.3", status="inactive")
        response = client.get("/api/dashboard")
        data = response.json()
        assert data["active_servers"] == 2
        assert data["total_servers"] == 3

    def test_total_apps_excludes_database_type_apps(self, client, isolated_config):
        _seed_server("srv", "1.1.1.1")
        _seed_app("srv", "web-app", app_type="git")
        _seed_app("srv", "pg-db", app_type="db:postgres")
        response = client.get("/api/dashboard")
        assert response.json()["total_apps"] == 1

    def test_running_apps_count_is_correct(self, client, isolated_config):
        _seed_server("srv", "1.1.1.1")
        _seed_app("srv", "running-1", status="running")
        _seed_app("srv", "running-2", status="running")
        _seed_app("srv", "stopped-1", status="stopped")
        response = client.get("/api/dashboard")
        data = response.json()
        assert data["running_apps"] == 2
        assert data["total_apps"] == 3

    def test_running_apps_excludes_database_type_even_if_running(self, client, isolated_config):
        _seed_server("srv", "1.1.1.1")
        _seed_app("srv", "web-app", status="running", app_type="git")
        _seed_app("srv", "pg-db", status="running", app_type="db:postgres")
        response = client.get("/api/dashboard")
        data = response.json()
        assert data["running_apps"] == 1

    def test_total_databases_counts_only_db_type_apps(self, client, isolated_config):
        _seed_server("srv", "1.1.1.1")
        _seed_app("srv", "web-app", app_type="git")
        _seed_app("srv", "pg-db", app_type="db:postgres")
        _seed_app("srv", "redis-db", app_type="db:redis")
        response = client.get("/api/dashboard")
        assert response.json()["total_databases"] == 2

    def test_recent_deployments_are_returned(self, client, isolated_config):
        _seed_server("srv", "1.1.1.1")
        app_id = _seed_app("srv", "my-app", status="running")
        init_db()
        with get_session() as session:
            dep = Deployment(app_id=app_id, status="success", log="build ok")
            session.add(dep)

        response = client.get("/api/dashboard")
        data = response.json()
        assert len(data["recent_deployments"]) == 1
        assert data["recent_deployments"][0]["status"] == "success"

    def test_recent_deployments_limited_to_10(self, client, isolated_config):
        _seed_server("srv", "1.1.1.1")
        app_id = _seed_app("srv", "busy-app")
        init_db()
        with get_session() as session:
            for i in range(15):
                dep = Deployment(app_id=app_id, status="success")
                session.add(dep)

        response = client.get("/api/dashboard")
        deployments = response.json()["recent_deployments"]
        assert len(deployments) <= 10

    def test_deployment_entry_includes_required_fields(self, client, isolated_config):
        _seed_server("srv", "1.1.1.1")
        app_id = _seed_app("srv", "my-app")
        init_db()
        with get_session() as session:
            dep = Deployment(app_id=app_id, status="failed", log="error details")
            session.add(dep)

        response = client.get("/api/dashboard")
        dep_data = response.json()["recent_deployments"][0]
        for field in ("id", "app_id", "status", "started_at"):
            assert field in dep_data

    def test_counts_are_independent_across_multiple_servers(self, client, isolated_config):
        _seed_server("prod", "1.1.1.1", status="active")
        _seed_server("staging", "2.2.2.2", status="active")
        _seed_server("dev", "3.3.3.3", status="inactive")
        _seed_app("prod", "api", status="running")
        _seed_app("staging", "frontend", status="stopped")
        response = client.get("/api/dashboard")
        data = response.json()
        assert data["total_servers"] == 3
        assert data["active_servers"] == 2
        assert data["total_apps"] == 2
        assert data["running_apps"] == 1
