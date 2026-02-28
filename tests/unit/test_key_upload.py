"""Tests for SSH key upload endpoint."""

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi.testclient import TestClient


@pytest.fixture
def client(isolated_config):
    from api.main import app

    return TestClient(app)


@pytest.fixture
def api_key(isolated_config):
    from cli.core.config import INFRAKT_HOME

    key_path = INFRAKT_HOME / "api_key.txt"
    key_path.parent.mkdir(parents=True, exist_ok=True)
    key_path.write_text("test-api-key")
    return "test-api-key"


@pytest.fixture
def ed25519_key_bytes():
    """Generate a valid Ed25519 private key in PEM format."""
    private_key = Ed25519PrivateKey.generate()
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    )


def test_upload_valid_key(client, api_key, ed25519_key_bytes):
    resp = client.post(
        "/api/keys/upload",
        headers={"X-API-Key": api_key},
        data={"name": "my-uploaded-key"},
        files={"file": ("id_ed25519", ed25519_key_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "my-uploaded-key"
    assert body["key_type"] == "ed25519"
    assert body["fingerprint"].startswith("SHA256:")
    assert body["public_key"].startswith("ssh-ed25519")


def test_upload_duplicate_name(client, api_key, ed25519_key_bytes):
    client.post(
        "/api/keys/upload",
        headers={"X-API-Key": api_key},
        data={"name": "dup-key"},
        files={"file": ("id_ed25519", ed25519_key_bytes, "application/octet-stream")},
    )
    resp = client.post(
        "/api/keys/upload",
        headers={"X-API-Key": api_key},
        data={"name": "dup-key"},
        files={"file": ("id_ed25519", ed25519_key_bytes, "application/octet-stream")},
    )
    assert resp.status_code == 409


def test_upload_invalid_file(client, api_key):
    resp = client.post(
        "/api/keys/upload",
        headers={"X-API-Key": api_key},
        data={"name": "bad-key"},
        files={"file": ("id_ed25519", b"not a real key", "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_upload_too_large(client, api_key):
    big_content = b"x" * 20_000
    resp = client.post(
        "/api/keys/upload",
        headers={"X-API-Key": api_key},
        data={"name": "big-key"},
        files={"file": ("id_ed25519", big_content, "application/octet-stream")},
    )
    assert resp.status_code == 400
