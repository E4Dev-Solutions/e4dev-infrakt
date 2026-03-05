"""Tests for multi-domain support in apps (domains + domain_ports)."""

import json
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
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})


def _seed_server(name="srv-1", host="1.2.3.4"):
    init_db()
    with get_session() as session:
        srv = Server(name=name, host=host, user="root", port=22, status="active")
        session.add(srv)
    return name


def _seed_app(server_name="srv-1", app_name="my-app", domain=None, domain_ports=None):
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
            domain=domain,
            domain_ports=domain_ports,
        )
        session.add(a)
    return app_name


# ---------------------------------------------------------------------------
# Create app with multi-domain
# ---------------------------------------------------------------------------


class TestCreateMultiDomain:
    def test_create_app_with_domains_and_domain_ports(self, client, isolated_config):
        _seed_server()
        response = client.post(
            "/api/apps",
            json={
                "name": "multi-app",
                "server_name": "srv-1",
                "port": 3000,
                "domains": {"frontend": "app.example.com", "api": "api.example.com"},
                "domain_ports": {"frontend": 3000, "api": 4000},
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["domains"] == {"frontend": "app.example.com", "api": "api.example.com"}
        assert data["domain_ports"] == {"frontend": 3000, "api": 4000}

    def test_create_app_domains_stored_as_json_in_domain_column(self, client, isolated_config):
        _seed_server()
        client.post(
            "/api/apps",
            json={
                "name": "json-app",
                "server_name": "srv-1",
                "port": 3000,
                "domains": {"web": "web.example.com"},
                "domain_ports": {"web": 8080},
            },
        )
        init_db()
        with get_session() as session:
            a = session.query(App).filter(App.name == "json-app").first()
            assert json.loads(a.domain) == {"web": "web.example.com"}
            assert json.loads(a.domain_ports) == {"web": 8080}


# ---------------------------------------------------------------------------
# _app_out includes domain_ports
# ---------------------------------------------------------------------------


class TestAppOutDomainPorts:
    def test_app_out_includes_domain_ports(self, client, isolated_config):
        _seed_app(
            domain=json.dumps({"svc": "svc.example.com"}),
            domain_ports=json.dumps({"svc": 5000}),
        )
        response = client.get("/api/apps")
        data = response.json()
        assert data[0]["domain_ports"] == {"svc": 5000}
        assert data[0]["domains"] == {"svc": "svc.example.com"}

    def test_app_out_domain_falls_back_to_first_value(self, client, isolated_config):
        _seed_app(domain=json.dumps({"a": "a.example.com", "b": "b.example.com"}))
        response = client.get("/api/apps")
        data = response.json()
        # domain should be the first value from the dict
        assert data[0]["domain"] == "a.example.com"

    def test_app_out_without_domain_ports(self, client, isolated_config):
        _seed_app(domain="simple.example.com")
        response = client.get("/api/apps")
        data = response.json()
        assert data[0]["domain"] == "simple.example.com"
        assert data[0]["domain_ports"] is None
        assert data[0]["domains"] is None


# ---------------------------------------------------------------------------
# Update app domains
# ---------------------------------------------------------------------------


class TestUpdateMultiDomain:
    def test_update_app_with_domains(self, client, isolated_config):
        _seed_app()
        response = client.put(
            "/api/apps/my-app",
            json={
                "domains": {"web": "web.example.com", "api": "api.example.com"},
                "domain_ports": {"web": 3000, "api": 4000},
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["domains"] == {"web": "web.example.com", "api": "api.example.com"}
        assert data["domain_ports"] == {"web": 3000, "api": 4000}

    def test_update_app_domains_stored_as_json(self, client, isolated_config):
        _seed_app()
        client.put(
            "/api/apps/my-app",
            json={"domains": {"svc": "svc.example.com"}},
        )
        init_db()
        with get_session() as session:
            a = session.query(App).filter(App.name == "my-app").first()
            assert json.loads(a.domain) == {"svc": "svc.example.com"}


# ---------------------------------------------------------------------------
# Destroy multi-domain app removes all proxy routes
# ---------------------------------------------------------------------------


class TestDestroyMultiDomain:
    def test_destroy_multi_domain_removes_all_routes(self, client, isolated_config):
        domains = json.dumps({"web": "web.example.com", "api": "api.example.com"})
        _seed_app(domain=domains)
        with (
            patch("api.routes.apps.SSHClient") as mock_cls,
            patch("api.routes.apps.destroy_app"),
            patch("api.routes.apps.remove_domain") as mock_remove,
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            client.delete("/api/apps/my-app")

        # Both domains should have been removed
        assert mock_remove.call_count == 2
        removed_domains = {call.args[1] for call in mock_remove.call_args_list}
        assert removed_domains == {"web.example.com", "api.example.com"}

    def test_destroy_single_domain_still_works(self, client, isolated_config):
        _seed_app(domain="simple.example.com")
        with (
            patch("api.routes.apps.SSHClient") as mock_cls,
            patch("api.routes.apps.destroy_app"),
            patch("api.routes.apps.remove_domain") as mock_remove,
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            client.delete("/api/apps/my-app")

        mock_remove.assert_called_once_with(mock_ssh, "simple.example.com")


# ---------------------------------------------------------------------------
# Schema validation
# ---------------------------------------------------------------------------


class TestSchemaValidation:
    def test_domain_ports_rejects_invalid_port(self, client, isolated_config):
        _seed_server()
        response = client.post(
            "/api/apps",
            json={
                "name": "bad-port-app",
                "server_name": "srv-1",
                "port": 3000,
                "domain_ports": {"svc": 99999},
            },
        )
        assert response.status_code == 422

    def test_domain_ports_rejects_zero_port(self, client, isolated_config):
        _seed_server()
        response = client.post(
            "/api/apps",
            json={
                "name": "zero-port-app",
                "server_name": "srv-1",
                "port": 3000,
                "domain_ports": {"svc": 0},
            },
        )
        assert response.status_code == 422
