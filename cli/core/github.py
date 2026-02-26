"""GitHub API integration and token storage for infrakt."""

from __future__ import annotations

from urllib.parse import urlparse, urlunparse

import httpx

from cli.core.crypto import decrypt, encrypt
from cli.core.database import get_session
from cli.models.github_integration import GitHubIntegration

GITHUB_API = "https://api.github.com"
REQUIRED_SCOPES = {"repo", "admin:repo_hook"}

# Keys to extract from the GitHub repos API response
_REPO_KEYS = {
    "full_name",
    "name",
    "private",
    "default_branch",
    "description",
    "html_url",
    "clone_url",
}


def _auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


# ── Token validation ─────────────────────────────────────────────


def validate_token(token: str) -> str:
    """Validate a GitHub token and return the username.

    Raises ValueError if the token is invalid or missing required scopes.
    """
    resp = httpx.get(f"{GITHUB_API}/user", headers=_auth_headers(token), timeout=15)

    if resp.status_code == 401:
        raise ValueError("Invalid GitHub token")

    data = resp.json()
    username = data["login"]

    # Check scopes
    scopes_header = resp.headers.get("x-oauth-scopes", "")
    granted = {s.strip() for s in scopes_header.split(",") if s.strip()}
    missing = REQUIRED_SCOPES - granted
    if missing:
        raise ValueError(f"Missing required scope(s): {', '.join(sorted(missing))}")

    return username


# ── Repository listing ───────────────────────────────────────────


def list_repos(token: str, per_page: int = 100) -> list[dict]:
    """Return all repos accessible to the token, paginated."""
    repos: list[dict] = []
    url: str | None = (
        f"{GITHUB_API}/user/repos?sort=updated&direction=desc&type=all"
        f"&per_page={per_page}"
    )

    while url:
        resp = httpx.get(url, headers=_auth_headers(token), timeout=15)
        resp.raise_for_status()

        for raw in resp.json():
            repo = {k: raw[k] for k in _REPO_KEYS if k in raw}
            owner = raw.get("owner", {})
            repo["owner"] = {
                "login": owner.get("login"),
                "avatar_url": owner.get("avatar_url"),
            }
            repos.append(repo)

        url = _next_page_url(resp.headers)

    return repos


def _next_page_url(headers: httpx.Headers | dict) -> str | None:
    """Parse the GitHub Link header for the next page URL."""
    link = headers.get("link") or headers.get("Link")
    if not link:
        return None
    for part in link.split(","):
        if 'rel="next"' in part:
            url = part.split(";")[0].strip().strip("<>")
            return url
    return None


# ── Webhook management ───────────────────────────────────────────


def create_repo_webhook(
    token: str, owner: str, repo: str, webhook_url: str, secret: str
) -> int | None:
    """Create a webhook on a GitHub repo. Returns hook ID or None on failure."""
    resp = httpx.post(
        f"{GITHUB_API}/repos/{owner}/{repo}/hooks",
        headers=_auth_headers(token),
        json={
            "name": "web",
            "active": True,
            "events": ["push"],
            "config": {
                "url": webhook_url,
                "content_type": "json",
                "secret": secret,
                "insecure_ssl": "0",
            },
        },
        timeout=15,
    )
    if resp.status_code == 201:
        return resp.json().get("id")
    return None


def delete_repo_webhook(token: str, owner: str, repo: str, hook_id: int) -> bool:
    """Delete a webhook from a GitHub repo. Returns True on success."""
    resp = httpx.delete(
        f"{GITHUB_API}/repos/{owner}/{repo}/hooks/{hook_id}",
        headers=_auth_headers(token),
        timeout=15,
    )
    return resp.status_code == 204


# ── URL token injection ──────────────────────────────────────────


def inject_token_in_url(url: str, token: str) -> str:
    """Rewrite a GitHub HTTPS URL to include the token for authenticated cloning.

    Non-GitHub URLs are returned unchanged.
    """
    parsed = urlparse(url)
    if parsed.hostname not in ("github.com", "www.github.com"):
        return url

    # Replace or set the netloc with the token
    netloc = f"{token}@{parsed.hostname}"
    if parsed.port:
        netloc += f":{parsed.port}"

    return urlunparse(parsed._replace(netloc=netloc))


# ── Token persistence ────────────────────────────────────────────


def save_github_token(token: str, username: str) -> None:
    """Encrypt and upsert the GitHub token into the database."""
    encrypted = encrypt(token)
    with get_session() as session:
        existing = session.query(GitHubIntegration).first()
        if existing:
            existing.token_encrypted = encrypted
            existing.github_username = username
        else:
            session.add(
                GitHubIntegration(
                    token_encrypted=encrypted,
                    github_username=username,
                )
            )


def get_github_token() -> str | None:
    """Read and decrypt the stored GitHub token, or return None."""
    with get_session() as session:
        row = session.query(GitHubIntegration).first()
        if row is None:
            return None
        return decrypt(row.token_encrypted)


def get_github_status() -> dict:
    """Return the current GitHub connection status."""
    with get_session() as session:
        row = session.query(GitHubIntegration).first()
        if row is None:
            return {"connected": False, "username": None}
        return {"connected": True, "username": row.github_username}


def delete_github_token() -> None:
    """Remove the GitHub integration row from the database."""
    with get_session() as session:
        row = session.query(GitHubIntegration).first()
        if row:
            session.delete(row)
