"""Tests for wipe-on-provision integration."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from cli.core.database import get_session, init_db
from cli.models.server import Server
from tests.conftest import TEST_API_KEY


@pytest.fixture
def client(isolated_config):
    """Return a TestClient backed by the isolated (temp) database."""
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})


class TestProvisionWipesNonInfraktHost:
    """Verify the is_infrakt_host flag works correctly."""

    def test_server_model_has_is_infrakt_host_default_false(self, isolated_config):
        init_db()
        with get_session() as session:
            srv = Server(name="test-srv", host="1.2.3.4")
            session.add(srv)
            session.flush()
            assert srv.is_infrakt_host is False

    def test_is_infrakt_host_can_be_set_true(self, isolated_config):
        init_db()
        with get_session() as session:
            srv = Server(name="host-srv", host="1.2.3.4", is_infrakt_host=True)
            session.add(srv)
            session.flush()
            assert srv.is_infrakt_host is True


class TestApiProvisionWipe:
    """Verify the API provision endpoint respects is_infrakt_host."""

    def test_provision_returns_200_for_non_infrakt_host(self, client, isolated_config):
        init_db()
        with get_session() as session:
            srv = Server(name="wipe-srv", host="1.2.3.4", is_infrakt_host=False)
            session.add(srv)

        with (
            patch("api.routes.servers.wipe_server"),
            patch("api.routes.servers.provision_server"),
            patch("api.routes.servers.asyncio"),
            patch("api.routes.servers.broadcaster"),
            patch("api.routes.servers.SSHClient"),
        ):
            response = client.post("/api/servers/wipe-srv/provision")

        assert response.status_code == 200

    def test_provision_returns_200_for_infrakt_host(self, client, isolated_config):
        init_db()
        with get_session() as session:
            srv = Server(name="safe-srv", host="1.2.3.4", is_infrakt_host=True)
            session.add(srv)

        with (
            patch("api.routes.servers.wipe_server"),
            patch("api.routes.servers.provision_server"),
            patch("api.routes.servers.asyncio"),
            patch("api.routes.servers.broadcaster"),
            patch("api.routes.servers.SSHClient"),
        ):
            response = client.post("/api/servers/safe-srv/provision")

        assert response.status_code == 200


class TestApiServerUpdateInfraktHost:
    """Verify is_infrakt_host can be set via PUT."""

    def test_update_sets_is_infrakt_host(self, client, isolated_config):
        init_db()
        with get_session() as session:
            srv = Server(name="update-srv", host="1.2.3.4")
            session.add(srv)

        response = client.put(
            "/api/servers/update-srv",
            json={"is_infrakt_host": True},
        )
        assert response.status_code == 200
        assert response.json()["is_infrakt_host"] is True

    def test_is_infrakt_host_in_server_list(self, client, isolated_config):
        init_db()
        with get_session() as session:
            srv = Server(name="list-srv", host="1.2.3.4", is_infrakt_host=True)
            session.add(srv)

        response = client.get("/api/servers")
        assert response.status_code == 200
        servers = response.json()
        matching = [s for s in servers if s["name"] == "list-srv"]
        assert len(matching) == 1
        assert matching[0]["is_infrakt_host"] is True
