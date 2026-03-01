"""Tests for S3 settings API endpoints."""

import pytest
from fastapi.testclient import TestClient

from api.main import app
from tests.conftest import TEST_API_KEY

HEADERS = {"X-API-Key": TEST_API_KEY}


@pytest.fixture
def client(isolated_config):
    return TestClient(app, headers=HEADERS)


class TestGetS3Config:
    def test_returns_empty_when_not_configured(self, client):
        resp = client.get("/api/settings/s3")
        assert resp.status_code == 200
        assert resp.json() == {"configured": False}

    def test_returns_config_with_masked_secret(self, client):
        client.put(
            "/api/settings/s3",
            json={
                "endpoint_url": "https://s3.amazonaws.com",
                "bucket": "my-backups",
                "region": "us-east-1",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "prefix": "infrakt/",
            },
        )
        resp = client.get("/api/settings/s3")
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["endpoint_url"] == "https://s3.amazonaws.com"
        assert data["bucket"] == "my-backups"
        assert data["access_key"] == "AKIAIOSFODNN7EXAMPLE"
        assert "secret_key" not in data


class TestPutS3Config:
    def test_saves_new_config(self, client):
        resp = client.put(
            "/api/settings/s3",
            json={
                "endpoint_url": "https://nyc3.digitaloceanspaces.com",
                "bucket": "backups",
                "region": "nyc3",
                "access_key": "DO_KEY",
                "secret_key": "DO_SECRET",
                "prefix": "",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "S3 configuration saved"

    def test_updates_existing_config(self, client):
        client.put(
            "/api/settings/s3",
            json={
                "endpoint_url": "https://s3.amazonaws.com",
                "bucket": "old-bucket",
                "region": "us-east-1",
                "access_key": "OLD_KEY",
                "secret_key": "OLD_SECRET",
                "prefix": "",
            },
        )
        resp = client.put(
            "/api/settings/s3",
            json={
                "endpoint_url": "https://s3.amazonaws.com",
                "bucket": "new-bucket",
                "region": "us-west-2",
                "access_key": "NEW_KEY",
                "secret_key": "NEW_SECRET",
                "prefix": "prod/",
            },
        )
        assert resp.status_code == 200
        get_resp = client.get("/api/settings/s3")
        assert get_resp.json()["bucket"] == "new-bucket"
        assert get_resp.json()["region"] == "us-west-2"


class TestDeleteS3Config:
    def test_deletes_existing_config(self, client):
        client.put(
            "/api/settings/s3",
            json={
                "endpoint_url": "https://s3.amazonaws.com",
                "bucket": "b",
                "region": "r",
                "access_key": "k",
                "secret_key": "s",
                "prefix": "",
            },
        )
        resp = client.delete("/api/settings/s3")
        assert resp.status_code == 200
        get_resp = client.get("/api/settings/s3")
        assert get_resp.json()["configured"] is False

    def test_delete_returns_200_even_when_not_configured(self, client):
        resp = client.delete("/api/settings/s3")
        assert resp.status_code == 200
