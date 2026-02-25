"""Deploy key management for CI/CD integration."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime
from typing import Any

from cli.core.config import INFRAKT_HOME

DEPLOY_KEYS_FILE = INFRAKT_HOME / "deploy_keys.json"


def _load_keys() -> list[dict[str, Any]]:
    if not DEPLOY_KEYS_FILE.exists():
        return []
    data = json.loads(DEPLOY_KEYS_FILE.read_text())
    return data if isinstance(data, list) else []


def _save_keys(keys: list[dict[str, Any]]) -> None:
    DEPLOY_KEYS_FILE.write_text(json.dumps(keys, indent=2))
    DEPLOY_KEYS_FILE.chmod(0o600)


def generate_deploy_key(label: str) -> str:
    """Generate a restricted deploy key. Returns the plaintext key (shown once)."""
    keys = _load_keys()
    if any(k["label"] == label for k in keys):
        raise ValueError(f"Deploy key with label '{label}' already exists")

    key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    keys.append(
        {
            "label": label,
            "key_hash": key_hash,
            "created_at": datetime.now(UTC).isoformat(),
            "scopes": ["deploy"],
        }
    )
    _save_keys(keys)
    return key


def validate_deploy_key(key: str) -> dict[str, Any] | None:
    """Validate a deploy key and return its metadata, or None if invalid."""
    key_hash = hashlib.sha256(key.encode()).hexdigest()
    keys = _load_keys()
    for k in keys:
        if k.get("key_hash") == key_hash:
            return k
    return None


def list_deploy_keys() -> list[dict[str, Any]]:
    """List all deploy keys (without revealing the key)."""
    return _load_keys()


def revoke_deploy_key(label: str) -> bool:
    """Remove a deploy key by label. Returns True if found and removed."""
    keys = _load_keys()
    new_keys = [k for k in keys if k["label"] != label]
    if len(new_keys) == len(keys):
        return False
    _save_keys(new_keys)
    return True
