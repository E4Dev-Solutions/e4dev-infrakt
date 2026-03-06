"""Tests for domain settings API endpoints."""
import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.conftest import TEST_API_KEY

HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture
def client(isolated_config):
    return TestClient(app, headers=HEADERS)


class TestGetDomainSettings:
    def test_returns_empty_when_not_configured(self, client):
        resp = client.get("/api/settings/domain")
        assert resp.status_code == 200
        assert resp.json() == {"base_domain": None}

    def test_returns_configured_domain(self, client):
        client.put("/api/settings/domain", json={"base_domain": "infrakt.cloud"})
        resp = client.get("/api/settings/domain")
        assert resp.status_code == 200
        assert resp.json() == {"base_domain": "infrakt.cloud"}


class TestPutDomainSettings:
    def test_saves_base_domain(self, client):
        resp = client.put("/api/settings/domain", json={"base_domain": "apps.example.com"})
        assert resp.status_code == 200
        assert resp.json()["message"] == "Domain settings saved"

    def test_updates_existing_domain(self, client):
        client.put("/api/settings/domain", json={"base_domain": "old.com"})
        client.put("/api/settings/domain", json={"base_domain": "new.com"})
        resp = client.get("/api/settings/domain")
        assert resp.json()["base_domain"] == "new.com"

    def test_clears_domain_with_null(self, client):
        client.put("/api/settings/domain", json={"base_domain": "infrakt.cloud"})
        client.put("/api/settings/domain", json={"base_domain": None})
        resp = client.get("/api/settings/domain")
        assert resp.json()["base_domain"] is None
