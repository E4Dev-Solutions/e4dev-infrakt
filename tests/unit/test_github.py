"""Tests for cli.core.github — GitHub API integration and token storage."""

from unittest.mock import MagicMock, patch

import pytest

from cli.core.database import init_db

# ── inject_token_in_url ──────────────────────────────────────────


def test_inject_token_in_url():
    from cli.core.github import inject_token_in_url

    result = inject_token_in_url("https://github.com/org/repo.git", "ghp_abc123")
    assert result == "https://ghp_abc123@github.com/org/repo.git"


def test_inject_token_in_url_non_github():
    from cli.core.github import inject_token_in_url

    url = "https://gitlab.com/org/repo.git"
    result = inject_token_in_url(url, "ghp_abc123")
    assert result == url


def test_inject_token_replaces_existing():
    from cli.core.github import inject_token_in_url

    result = inject_token_in_url("https://old_token@github.com/org/repo.git", "ghp_new")
    assert result == "https://ghp_new@github.com/org/repo.git"


# ── validate_token ───────────────────────────────────────────────


def test_validate_token_success():
    from cli.core.github import validate_token

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"login": "octocat"}
    mock_response.headers = {"x-oauth-scopes": "repo, admin:repo_hook, read:org"}

    with patch("cli.core.github.httpx.get", return_value=mock_response):
        username = validate_token("ghp_valid")
    assert username == "octocat"


def test_validate_token_invalid():
    from cli.core.github import validate_token

    mock_response = MagicMock()
    mock_response.status_code = 401

    with patch("cli.core.github.httpx.get", return_value=mock_response):
        with pytest.raises(ValueError, match="Invalid GitHub token"):
            validate_token("ghp_bad")


def test_validate_token_missing_scopes():
    from cli.core.github import validate_token

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"login": "octocat"}
    mock_response.headers = {"x-oauth-scopes": "read:org"}

    with patch("cli.core.github.httpx.get", return_value=mock_response):
        with pytest.raises(ValueError, match="Missing required scope"):
            validate_token("ghp_limited")


# ── list_repos ───────────────────────────────────────────────────


def test_list_repos():
    from cli.core.github import list_repos

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = [
        {
            "full_name": "octocat/hello",
            "name": "hello",
            "private": False,
            "default_branch": "main",
            "description": "A test repo",
            "html_url": "https://github.com/octocat/hello",
            "clone_url": "https://github.com/octocat/hello.git",
            "owner": {"login": "octocat", "avatar_url": "https://avatar.url/1"},
            "extra_field": "ignored",
        }
    ]
    mock_response.headers = {}  # no Link header = single page

    with patch("cli.core.github.httpx.get", return_value=mock_response):
        repos = list_repos("ghp_token")

    assert len(repos) == 1
    assert repos[0]["full_name"] == "octocat/hello"
    assert repos[0]["owner"]["login"] == "octocat"
    assert "extra_field" not in repos[0]


# ── save / get / delete token (DB round-trip) ───────────────────


def test_save_and_get_github_token(isolated_config):
    from cli.core.github import get_github_token, save_github_token

    init_db()

    save_github_token("ghp_secret_123", "octocat")
    retrieved = get_github_token()
    assert retrieved == "ghp_secret_123"


def test_delete_github_token(isolated_config):
    from cli.core.github import delete_github_token, get_github_token, save_github_token

    init_db()

    save_github_token("ghp_to_delete", "octocat")
    assert get_github_token() is not None

    delete_github_token()
    assert get_github_token() is None
