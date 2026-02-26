"""GitHub integration API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from api.schemas import GitHubConnect, GitHubRepo, GitHubStatus
from cli.core.database import init_db
from cli.core.github import (
    delete_github_token,
    get_github_status,
    get_github_token,
    list_repos,
    save_github_token,
    validate_token,
)

router = APIRouter(prefix="/github", tags=["github"])


@router.get("/status", response_model=GitHubStatus)
def status() -> dict:
    init_db()
    return get_github_status()


@router.post("/connect", response_model=GitHubStatus)
def connect(body: GitHubConnect) -> dict:
    init_db()
    try:
        username = validate_token(body.token)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    save_github_token(body.token, username)
    return {"connected": True, "username": username}


@router.delete("/disconnect")
def disconnect() -> dict[str, str]:
    init_db()
    delete_github_token()
    return {"message": "GitHub disconnected"}


@router.get("/repos", response_model=list[GitHubRepo])
def repos() -> list[dict]:
    init_db()
    token = get_github_token()
    if token is None:
        raise HTTPException(400, "GitHub not connected. Add a PAT in Settings first.")
    return list_repos(token)
