from unittest.mock import patch
from fastapi.testclient import TestClient
from api.main import app
from cli.core.database import init_db
from tests.conftest import TEST_API_KEY

client = TestClient(app)
HEADERS = {"X-API-Key": TEST_API_KEY}

def test_github_status_disconnected():
    init_db()
    resp = client.get("/api/github/status", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["connected"] is False
    assert resp.json()["username"] is None

@patch("api.routes.github.validate_token")
def test_github_connect(mock_validate):
    mock_validate.return_value = "testuser"
    init_db()
    resp = client.post("/api/github/connect", json={"token": "ghp_test123"}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["connected"] is True
    assert resp.json()["username"] == "testuser"

@patch("api.routes.github.validate_token")
def test_github_connect_then_status(mock_validate):
    mock_validate.return_value = "testuser"
    init_db()
    client.post("/api/github/connect", json={"token": "ghp_test123"}, headers=HEADERS)
    resp = client.get("/api/github/status", headers=HEADERS)
    assert resp.json()["connected"] is True
    assert resp.json()["username"] == "testuser"

@patch("api.routes.github.validate_token")
def test_github_disconnect(mock_validate):
    mock_validate.return_value = "testuser"
    init_db()
    client.post("/api/github/connect", json={"token": "ghp_test123"}, headers=HEADERS)
    resp = client.delete("/api/github/disconnect", headers=HEADERS)
    assert resp.status_code == 200
    resp = client.get("/api/github/status", headers=HEADERS)
    assert resp.json()["connected"] is False

@patch("api.routes.github.validate_token")
def test_github_connect_invalid_token(mock_validate):
    mock_validate.side_effect = ValueError("Invalid GitHub token")
    init_db()
    resp = client.post("/api/github/connect", json={"token": "bad"}, headers=HEADERS)
    assert resp.status_code == 400
    assert "Invalid GitHub token" in resp.json()["detail"]

@patch("api.routes.github.list_repos")
@patch("api.routes.github.get_github_token")
def test_github_repos(mock_get_token, mock_list):
    mock_get_token.return_value = "ghp_test123"
    mock_list.return_value = [{"full_name": "org/repo1", "name": "repo1", "private": False, "default_branch": "main", "description": "A repo", "html_url": "https://github.com/org/repo1", "clone_url": "https://github.com/org/repo1.git", "owner": {"login": "org", "avatar_url": ""}}]
    init_db()
    resp = client.get("/api/github/repos", headers=HEADERS)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert resp.json()[0]["full_name"] == "org/repo1"

@patch("api.routes.github.get_github_token")
def test_github_repos_not_connected(mock_get_token):
    mock_get_token.return_value = None
    init_db()
    resp = client.get("/api/github/repos", headers=HEADERS)
    assert resp.status_code == 400
    assert "not connected" in resp.json()["detail"].lower()
