"""Tests for FastAPI /api/servers routes."""

from unittest.mock import MagicMock, patch

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


def _seed_server(name="srv-1", host="1.2.3.4", user="root", status="active"):
    """Insert a server directly into the isolated DB."""
    init_db()
    with get_session() as session:
        srv = Server(name=name, host=host, user=user, port=22, status=status)
        session.add(srv)
    return name


# ---------------------------------------------------------------------------
# GET /api/servers
# ---------------------------------------------------------------------------


class TestListServers:
    def test_returns_empty_list_when_no_servers(self, client):
        response = client.get("/api/servers")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_registered_servers(self, client, isolated_config):
        _seed_server("web-01")
        response = client.get("/api/servers")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "web-01"

    def test_returns_servers_sorted_by_name(self, client, isolated_config):
        _seed_server("zebra", host="3.3.3.3")
        _seed_server("alpha", host="1.1.1.1")
        _seed_server("mango", host="2.2.2.2")
        response = client.get("/api/servers")
        names = [s["name"] for s in response.json()]
        assert names == sorted(names)

    def test_server_response_includes_expected_fields(self, client, isolated_config):
        _seed_server("check-fields", host="5.5.5.5")
        response = client.get("/api/servers")
        srv = response.json()[0]
        for field in ("id", "name", "host", "user", "port", "status", "app_count"):
            assert field in srv

    def test_app_count_reflects_seeded_apps(self, client, isolated_config):
        # app_count should be 0 for a server with no apps
        _seed_server("lonely")
        response = client.get("/api/servers")
        assert response.json()[0]["app_count"] == 0


# ---------------------------------------------------------------------------
# POST /api/servers
# ---------------------------------------------------------------------------


class TestAddServer:
    def test_creates_server_and_returns_201(self, client, isolated_config):
        payload = {"name": "new-srv", "host": "9.9.9.9", "user": "root", "port": 22}
        response = client.post("/api/servers", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "new-srv"
        assert data["host"] == "9.9.9.9"

    def test_created_server_has_inactive_status(self, client, isolated_config):
        payload = {"name": "fresh-srv", "host": "7.7.7.7"}
        response = client.post("/api/servers", json=payload)
        assert response.status_code == 201
        assert response.json()["status"] == "inactive"

    def test_returns_400_on_duplicate_server_name(self, client, isolated_config):
        payload = {"name": "dup-srv", "host": "1.1.1.1"}
        client.post("/api/servers", json=payload)
        response = client.post("/api/servers", json=payload)
        assert response.status_code == 400
        assert "dup-srv" in response.json()["detail"]

    def test_returns_422_when_name_missing(self, client, isolated_config):
        response = client.post("/api/servers", json={"host": "1.1.1.1"})
        assert response.status_code == 422

    def test_returns_422_when_host_missing(self, client, isolated_config):
        response = client.post("/api/servers", json={"name": "no-host"})
        assert response.status_code == 422

    def test_accepts_optional_ssh_key_path(self, client, isolated_config):
        payload = {
            "name": "key-srv",
            "host": "8.8.8.8",
            "ssh_key_path": "/home/user/.ssh/id_rsa",
        }
        response = client.post("/api/servers", json=payload)
        assert response.status_code == 201
        assert response.json()["ssh_key_path"] == "/home/user/.ssh/id_rsa"

    def test_rejects_name_with_special_characters(self, client, isolated_config):
        payload = {"name": "bad name!", "host": "1.1.1.1"}
        response = client.post("/api/servers", json=payload)
        assert response.status_code == 422

    def test_default_port_is_22(self, client, isolated_config):
        payload = {"name": "port-default", "host": "1.2.3.4"}
        response = client.post("/api/servers", json=payload)
        assert response.status_code == 201
        assert response.json()["port"] == 22


# ---------------------------------------------------------------------------
# DELETE /api/servers/{name}
# ---------------------------------------------------------------------------


class TestRemoveServer:
    def test_removes_existing_server_and_returns_message(self, client, isolated_config):
        _seed_server("to-remove")
        response = client.delete("/api/servers/to-remove")
        assert response.status_code == 200
        assert "to-remove" in response.json()["message"]

    def test_server_is_gone_after_deletion(self, client, isolated_config):
        _seed_server("gone-srv")
        client.delete("/api/servers/gone-srv")
        response = client.get("/api/servers")
        names = [s["name"] for s in response.json()]
        assert "gone-srv" not in names

    def test_returns_404_when_server_not_found(self, client, isolated_config):
        response = client.delete("/api/servers/no-such-server")
        assert response.status_code == 404
        assert "no-such-server" in response.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/servers/{name}/test
# ---------------------------------------------------------------------------


class TestConnectionTest:
    def test_returns_reachable_true_when_ssh_succeeds(self, client, isolated_config):
        _seed_server("reach-me")
        with patch("api.routes.servers.SSHClient") as mock_cls:
            mock_ssh = MagicMock()
            mock_ssh.test_connection.return_value = True
            mock_cls.from_server.return_value = mock_ssh
            response = client.post("/api/servers/reach-me/test")

        assert response.status_code == 200
        assert response.json()["reachable"] is True

    def test_returns_reachable_false_when_ssh_fails(self, client, isolated_config):
        _seed_server("unreachable")
        with patch("api.routes.servers.SSHClient") as mock_cls:
            mock_ssh = MagicMock()
            mock_ssh.test_connection.return_value = False
            mock_cls.from_server.return_value = mock_ssh
            response = client.post("/api/servers/unreachable/test")

        assert response.status_code == 200
        assert response.json()["reachable"] is False

    def test_returns_404_when_server_not_found(self, client, isolated_config):
        response = client.post("/api/servers/ghost/test")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/servers/{name}/status
# ---------------------------------------------------------------------------


class TestServerStatus:
    def test_returns_structured_memory_and_disk(self, client, isolated_config):
        _seed_server("status-srv")
        with patch("api.routes.servers.SSHClient") as mock_cls:
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_ssh.run_checked.return_value = "up 2 days"
            mock_ssh.run.side_effect = [
                ("8000000000 2000000000 5000000000", "", 0),  # free -b
                ("20000000000 5000000000 15000000000 25%", "", 0),  # df -B1
                ("", "", 0),  # docker ps
            ]
            mock_cls.from_server.return_value = mock_ssh
            response = client.get("/api/servers/status-srv/status")

        assert response.status_code == 200
        data = response.json()
        assert data["uptime"] == "up 2 days"
        assert isinstance(data["memory"], dict)
        assert "percent" in data["memory"]
        assert isinstance(data["memory"]["percent"], float)
        assert isinstance(data["disk"], dict)
        assert isinstance(data["disk"]["percent"], float)
        assert isinstance(data["containers"], list)

    def test_returns_containers_from_docker_ps(self, client, isolated_config):
        _seed_server("docker-srv")
        docker_json = '{"ID":"abc123","Names":"web","Status":"Up 1 hour","Image":"nginx"}\n'
        with patch("api.routes.servers.SSHClient") as mock_cls:
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_ssh.run_checked.return_value = "up 1 day"
            mock_ssh.run.side_effect = [
                ("4000000000 1000000000 3000000000", "", 0),
                ("10000000000 2000000000 8000000000 20%", "", 0),
                (docker_json, "", 0),
            ]
            mock_cls.from_server.return_value = mock_ssh
            response = client.get("/api/servers/docker-srv/status")

        data = response.json()
        assert len(data["containers"]) == 1
        assert data["containers"][0]["name"] == "web"
        assert data["containers"][0]["id"] == "abc123"


# ---------------------------------------------------------------------------
# POST /api/servers/{name}/provision
# ---------------------------------------------------------------------------


class TestProvision:
    def test_returns_provision_key_in_response(self, client, isolated_config):
        _seed_server("prov-srv", status="inactive")
        mock_loop = MagicMock()
        with (
            patch("api.routes.servers.provision_server"),
            patch("api.routes.servers.asyncio.get_event_loop", return_value=mock_loop),
            patch("api.routes.servers.broadcaster"),
        ):
            response = client.post("/api/servers/prov-srv/provision")

        assert response.status_code == 200
        data = response.json()
        assert "provision_key" in data
        assert isinstance(data["provision_key"], int)
        assert data["provision_key"] < 0  # negative server ID

    def test_returns_404_for_unknown_server(self, client, isolated_config):
        response = client.post("/api/servers/ghost/provision")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/servers/{name}/provision/stream
# ---------------------------------------------------------------------------


class TestProvisionStream:
    def test_returns_404_for_unknown_server(self, client, isolated_config):
        response = client.get("/api/servers/ghost/provision/stream?key=-999")
        assert response.status_code == 404

    def test_returns_done_event_when_already_finished(self, client, isolated_config):
        _seed_server("done-srv", status="active")
        response = client.get("/api/servers/done-srv/provision/stream?key=-999")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        body = response.text
        assert '"done": true' in body
        assert '"status": "active"' in body
