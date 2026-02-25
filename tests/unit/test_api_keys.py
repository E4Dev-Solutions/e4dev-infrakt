"""Tests for FastAPI /api/keys routes — SSH key management API."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from cli.core.database import get_session, init_db
from cli.models.server import Server
from cli.models.ssh_key import SSHKey
from tests.conftest import TEST_API_KEY


@pytest.fixture
def client(isolated_config):
    """Return a TestClient backed by the isolated (temp) database."""
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})


def _seed_server(name="prod-1", host="1.2.3.4", user="root") -> str:
    """Insert a Server into the isolated DB and return its name."""
    init_db()
    with get_session() as session:
        srv = Server(name=name, host=host, user=user, port=22, status="active")
        session.add(srv)
    return name


def _seed_ssh_key(
    name="my-key", fingerprint="SHA256:abc123", public_key="ssh-ed25519 AAAAC3 x"
) -> int:
    """Insert an SSHKey into the isolated DB and return its id."""
    init_db()
    with get_session() as session:
        key = SSHKey(
            name=name,
            fingerprint=fingerprint,
            key_type="ed25519",
            public_key=public_key,
            key_path=f"/tmp/keys/{name}",
        )
        session.add(key)
        session.flush()
        return key.id


# ---------------------------------------------------------------------------
# GET /api/keys
# ---------------------------------------------------------------------------


class TestListKeys:
    def test_returns_empty_list_when_no_keys(self, client, isolated_config):
        init_db()
        response = client.get("/api/keys")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_seeded_key(self, client, isolated_config):
        _seed_ssh_key("my-key")
        response = client.get("/api/keys")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["name"] == "my-key"

    def test_response_includes_expected_fields(self, client, isolated_config):
        _seed_ssh_key("field-key")
        data = client.get("/api/keys").json()[0]
        for field in ("id", "name", "fingerprint", "key_type", "public_key", "created_at"):
            assert field in data

    def test_key_type_is_ed25519(self, client, isolated_config):
        _seed_ssh_key("type-key")
        data = client.get("/api/keys").json()[0]
        assert data["key_type"] == "ed25519"

    def test_returns_multiple_keys(self, client, isolated_config):
        _seed_ssh_key("key-one", fingerprint="SHA256:aaa")
        _seed_ssh_key("key-two", fingerprint="SHA256:bbb")
        data = client.get("/api/keys").json()
        assert len(data) == 2

    def test_requires_api_key_auth(self, isolated_config):
        unauthenticated = TestClient(app)
        response = unauthenticated.get("/api/keys")
        assert response.status_code in (401, 403)


# ---------------------------------------------------------------------------
# POST /api/keys
# ---------------------------------------------------------------------------


class TestGenerateKey:
    def test_creates_key_and_returns_201(self, client, isolated_config):
        with (
            patch("api.routes.keys.generate_key") as mock_gen,
            patch("api.routes.keys.get_public_key") as mock_pub,
        ):
            mock_gen.return_value = (isolated_config / "keys" / "new-key", "SHA256:xyz")
            mock_pub.return_value = "ssh-ed25519 AAAAC3 new"
            response = client.post("/api/keys", json={"name": "new-key"})

        assert response.status_code == 201

    def test_response_contains_name(self, client, isolated_config):
        with (
            patch("api.routes.keys.generate_key") as mock_gen,
            patch("api.routes.keys.get_public_key") as mock_pub,
        ):
            mock_gen.return_value = (isolated_config / "keys" / "resp-key", "SHA256:xyz")
            mock_pub.return_value = "ssh-ed25519 AAAAC3 x"
            response = client.post("/api/keys", json={"name": "resp-key"})

        assert response.json()["name"] == "resp-key"

    def test_response_contains_fingerprint(self, client, isolated_config):
        with (
            patch("api.routes.keys.generate_key") as mock_gen,
            patch("api.routes.keys.get_public_key") as mock_pub,
        ):
            mock_gen.return_value = (isolated_config / "keys" / "fp-key", "SHA256:fingerprint123")
            mock_pub.return_value = "ssh-ed25519 AAAAC3 x"
            response = client.post("/api/keys", json={"name": "fp-key"})

        assert response.json()["fingerprint"] == "SHA256:fingerprint123"

    def test_key_is_persisted_in_database(self, client, isolated_config):
        with (
            patch("api.routes.keys.generate_key") as mock_gen,
            patch("api.routes.keys.get_public_key") as mock_pub,
        ):
            mock_gen.return_value = (isolated_config / "keys" / "persist-key", "SHA256:p")
            mock_pub.return_value = "ssh-ed25519 AAAAC3 x"
            client.post("/api/keys", json={"name": "persist-key"})

        response = client.get("/api/keys")
        names = [k["name"] for k in response.json()]
        assert "persist-key" in names

    def test_duplicate_name_returns_409(self, client, isolated_config):
        _seed_ssh_key("dup-key")
        with (
            patch("api.routes.keys.generate_key") as mock_gen,
            patch("api.routes.keys.get_public_key") as mock_pub,
        ):
            mock_gen.return_value = (isolated_config / "keys" / "dup-key", "SHA256:x")
            mock_pub.return_value = "ssh-ed25519 AAAAC3 x"
            response = client.post("/api/keys", json={"name": "dup-key"})

        assert response.status_code == 409
        assert "dup-key" in response.json()["detail"]

    def test_missing_name_returns_422(self, client, isolated_config):
        response = client.post("/api/keys", json={})
        assert response.status_code == 422

    def test_key_generation_failure_returns_400(self, client, isolated_config):
        with patch("api.routes.keys.generate_key", side_effect=Exception("disk full")):
            response = client.post("/api/keys", json={"name": "fail-key"})
        assert response.status_code == 400
        assert "Key generation failed" in response.json()["detail"]


# ---------------------------------------------------------------------------
# DELETE /api/keys/{name}
# ---------------------------------------------------------------------------


class TestDeleteKey:
    def test_delete_returns_200(self, client, isolated_config):
        _seed_ssh_key("del-key")
        with patch("api.routes.keys.remove_key_files"):
            response = client.delete("/api/keys/del-key")
        assert response.status_code == 200

    def test_delete_returns_success_message(self, client, isolated_config):
        _seed_ssh_key("bye-key")
        with patch("api.routes.keys.remove_key_files"):
            response = client.delete("/api/keys/bye-key")
        assert "bye-key" in response.json()["message"]

    def test_delete_removes_key_from_database(self, client, isolated_config):
        _seed_ssh_key("gone-key")
        with patch("api.routes.keys.remove_key_files"):
            client.delete("/api/keys/gone-key")

        init_db()
        with get_session() as session:
            key = session.query(SSHKey).filter(SSHKey.name == "gone-key").first()
        assert key is None

    def test_delete_nonexistent_key_returns_404(self, client, isolated_config):
        init_db()
        response = client.delete("/api/keys/ghost-key")
        assert response.status_code == 404
        assert "ghost-key" in response.json()["detail"]

    def test_delete_calls_remove_key_files(self, client, isolated_config):
        _seed_ssh_key("files-key")
        with patch("api.routes.keys.remove_key_files") as mock_remove:
            client.delete("/api/keys/files-key")
        mock_remove.assert_called_once_with("files-key")


# ---------------------------------------------------------------------------
# POST /api/keys/{name}/deploy
# ---------------------------------------------------------------------------


class TestDeployKey:
    def test_deploy_returns_200(self, client, isolated_config):
        _seed_server("prod-1")
        _seed_ssh_key("deploy-key")
        with (
            patch("api.routes.keys.SSHClient") as mock_cls,
            patch("api.routes.keys.deploy_key_to_server"),
        ):
            mock_ssh = MagicMock()
            mock_cls.from_server.return_value = mock_ssh
            mock_ssh.close = MagicMock()
            response = client.post("/api/keys/deploy-key/deploy", json={"server_name": "prod-1"})

        assert response.status_code == 200

    def test_deploy_returns_success_message(self, client, isolated_config):
        _seed_server("srv-x")
        _seed_ssh_key("msg-key")
        with (
            patch("api.routes.keys.SSHClient") as mock_cls,
            patch("api.routes.keys.deploy_key_to_server"),
        ):
            mock_ssh = MagicMock()
            mock_cls.from_server.return_value = mock_ssh
            mock_ssh.close = MagicMock()
            response = client.post("/api/keys/msg-key/deploy", json={"server_name": "srv-x"})

        data = response.json()
        assert "msg-key" in data["message"]
        assert "srv-x" in data["message"]

    def test_deploy_nonexistent_key_returns_404(self, client, isolated_config):
        _seed_server("prod-1")
        response = client.post("/api/keys/no-such-key/deploy", json={"server_name": "prod-1"})
        assert response.status_code == 404
        assert "no-such-key" in response.json()["detail"]

    def test_deploy_nonexistent_server_returns_404(self, client, isolated_config):
        _seed_ssh_key("orphan-key")
        response = client.post(
            "/api/keys/orphan-key/deploy", json={"server_name": "no-such-server"}
        )
        assert response.status_code == 404
        assert "no-such-server" in response.json()["detail"]

    def test_deploy_ssh_failure_returns_500(self, client, isolated_config):
        from cli.core.exceptions import SSHConnectionError

        _seed_server("bad-srv")
        _seed_ssh_key("fail-key")
        with (
            patch("api.routes.keys.SSHClient") as mock_cls,
            patch(
                "api.routes.keys.deploy_key_to_server", side_effect=SSHConnectionError("refused")
            ),
        ):
            mock_ssh = MagicMock()
            mock_cls.from_server.return_value = mock_ssh
            mock_ssh.close = MagicMock()
            response = client.post("/api/keys/fail-key/deploy", json={"server_name": "bad-srv"})

        assert response.status_code == 500
        assert "Failed to deploy key" in response.json()["detail"]
