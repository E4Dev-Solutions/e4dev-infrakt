"""API key authentication for infrakt API."""

import hashlib
import hmac
import secrets
from pathlib import Path

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

import cli.core.config as config

API_KEY_FILE = "api_key.txt"

_api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def _api_key_path() -> Path:
    return config.INFRAKT_HOME / API_KEY_FILE


def get_or_create_api_key() -> str:
    """Read or generate the API key. Returns the plaintext key."""
    config.ensure_config_dir()
    path = _api_key_path()
    if path.exists():
        return path.read_text().strip()
    key = secrets.token_urlsafe(32)
    path.write_text(key)
    path.chmod(0o600)
    return key


def require_api_key(api_key: str | None = Security(_api_key_header)) -> str:
    """FastAPI dependency that validates the X-API-Key header."""
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    expected = get_or_create_api_key()
    if not hmac.compare_digest(
        hashlib.sha256(api_key.encode()).digest(),
        hashlib.sha256(expected.encode()).digest(),
    ):
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
