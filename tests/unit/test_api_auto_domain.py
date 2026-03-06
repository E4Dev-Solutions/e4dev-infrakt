"""Tests for auto-domain assignment on app create."""

import re

import pytest
from fastapi.testclient import TestClient

from api.main import app
from cli.core.database import get_session, init_db
from cli.models.platform_settings import PlatformSettings
from cli.models.server import Server
from tests.conftest import TEST_API_KEY

HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture
def client(isolated_config):
    return TestClient(app, headers=HEADERS)


@pytest.fixture
def server_with_domain(client):
    """Create a server and configure base_domain."""
    client.post(
        "/api/servers",
        json={"name": "test-srv", "host": "1.2.3.4", "user": "root"},
    )
    init_db()
    with get_session() as session:
        session.add(PlatformSettings(base_domain="infrakt.cloud"))
    return "test-srv"


class TestAutoDomainOnCreate:
    def test_assigns_random_domain_when_none_provided(self, client, server_with_domain):
        resp = client.post(
            "/api/apps",
            json={"name": "myapp", "server_name": server_with_domain, "image": "nginx"},
        )
        assert resp.status_code == 201
        domain = resp.json()["domain"]
        assert domain is not None
        assert domain.endswith(".infrakt.cloud")
        assert re.match(r"^[a-f0-9]{8}\.infrakt\.cloud$", domain)

    def test_no_auto_domain_when_explicit_domain_set(self, client, server_with_domain):
        resp = client.post(
            "/api/apps",
            json={
                "name": "myapp2",
                "server_name": server_with_domain,
                "image": "nginx",
                "domain": "custom.example.com",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["domain"] == "custom.example.com"

    def test_no_auto_domain_when_base_domain_not_configured(self, client):
        client.post(
            "/api/servers",
            json={"name": "bare-srv", "host": "5.6.7.8", "user": "root"},
        )
        resp = client.post(
            "/api/apps",
            json={"name": "nodom", "server_name": "bare-srv", "image": "nginx"},
        )
        assert resp.status_code == 201
        assert resp.json()["domain"] is None
