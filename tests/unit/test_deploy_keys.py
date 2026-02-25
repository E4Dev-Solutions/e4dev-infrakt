"""Tests for cli/core/deploy_keys.py — deploy key generation, validation, and management."""

from __future__ import annotations

import hashlib
import json

import pytest

import cli.core.deploy_keys as dk_mod
from cli.core.deploy_keys import (
    generate_deploy_key,
    list_deploy_keys,
    revoke_deploy_key,
    validate_deploy_key,
)


@pytest.fixture(autouse=True)
def patch_deploy_keys_file(isolated_config, monkeypatch):
    """Redirect DEPLOY_KEYS_FILE to the isolated temp directory."""
    deploy_keys_path = isolated_config / "deploy_keys.json"
    monkeypatch.setattr(dk_mod, "DEPLOY_KEYS_FILE", deploy_keys_path)
    return deploy_keys_path


# ---------------------------------------------------------------------------
# generate_deploy_key
# ---------------------------------------------------------------------------


class TestGenerateDeployKey:
    def test_returns_plaintext_key_string(self):
        key = generate_deploy_key("ci-deploy")
        assert isinstance(key, str)
        assert len(key) > 0

    def test_key_is_url_safe_token_format(self):
        import re

        key = generate_deploy_key("ci-key")
        assert re.match(r"^[A-Za-z0-9_\-]+$", key)

    def test_key_is_stored_as_hash_not_plaintext(self):
        key = generate_deploy_key("hashed-key")
        keys_data = json.loads(dk_mod.DEPLOY_KEYS_FILE.read_text())
        stored_entry = keys_data[0]
        # Plaintext key must NOT appear in the file
        assert key not in json.dumps(stored_entry)
        # The hash must be the SHA-256 hex digest of the key
        expected_hash = hashlib.sha256(key.encode()).hexdigest()
        assert stored_entry["key_hash"] == expected_hash

    def test_label_is_stored_in_file(self):
        generate_deploy_key("my-ci")
        keys_data = json.loads(dk_mod.DEPLOY_KEYS_FILE.read_text())
        assert keys_data[0]["label"] == "my-ci"

    def test_scopes_contain_deploy(self):
        generate_deploy_key("scoped-key")
        keys_data = json.loads(dk_mod.DEPLOY_KEYS_FILE.read_text())
        assert "deploy" in keys_data[0]["scopes"]

    def test_created_at_is_stored(self):
        generate_deploy_key("ts-key")
        keys_data = json.loads(dk_mod.DEPLOY_KEYS_FILE.read_text())
        assert "created_at" in keys_data[0]

    def test_duplicate_label_raises_value_error(self):
        generate_deploy_key("dup-label")
        with pytest.raises(ValueError, match="already exists"):
            generate_deploy_key("dup-label")

    def test_each_call_returns_unique_key(self):
        key1 = generate_deploy_key("key-one")
        key2 = generate_deploy_key("key-two")
        assert key1 != key2

    def test_key_file_has_restricted_permissions(self):
        generate_deploy_key("perm-key")
        mode = oct(dk_mod.DEPLOY_KEYS_FILE.stat().st_mode)[-3:]
        assert mode == "600"

    def test_multiple_keys_are_accumulated(self):
        generate_deploy_key("alpha")
        generate_deploy_key("beta")
        keys_data = json.loads(dk_mod.DEPLOY_KEYS_FILE.read_text())
        assert len(keys_data) == 2


# ---------------------------------------------------------------------------
# validate_deploy_key
# ---------------------------------------------------------------------------


class TestValidateDeployKey:
    def test_valid_key_returns_metadata(self):
        key = generate_deploy_key("valid-label")
        metadata = validate_deploy_key(key)
        assert metadata is not None
        assert metadata["label"] == "valid-label"

    def test_invalid_key_returns_none(self):
        generate_deploy_key("some-key")
        result = validate_deploy_key("totally-wrong-key")
        assert result is None

    def test_empty_key_store_returns_none(self):
        result = validate_deploy_key("any-key")
        assert result is None

    def test_metadata_contains_scopes(self):
        key = generate_deploy_key("scope-check")
        metadata = validate_deploy_key(key)
        assert "scopes" in metadata
        assert "deploy" in metadata["scopes"]

    def test_metadata_does_not_contain_plaintext_key(self):
        key = generate_deploy_key("no-plaintext")
        metadata = validate_deploy_key(key)
        assert key not in json.dumps(metadata)

    def test_revoked_key_returns_none(self):
        key = generate_deploy_key("to-revoke")
        revoke_deploy_key("to-revoke")
        assert validate_deploy_key(key) is None


# ---------------------------------------------------------------------------
# list_deploy_keys
# ---------------------------------------------------------------------------


class TestListDeployKeys:
    def test_empty_when_no_keys_exist(self):
        result = list_deploy_keys()
        assert result == []

    def test_returns_list_of_dicts(self):
        generate_deploy_key("list-key")
        result = list_deploy_keys()
        assert isinstance(result, list)
        assert isinstance(result[0], dict)

    def test_returns_all_generated_keys(self):
        generate_deploy_key("list-alpha")
        generate_deploy_key("list-beta")
        result = list_deploy_keys()
        assert len(result) == 2

    def test_list_does_not_contain_plaintext_keys(self):
        key = generate_deploy_key("no-leak")
        result_json = json.dumps(list_deploy_keys())
        assert key not in result_json

    def test_list_contains_labels(self):
        generate_deploy_key("label-alpha")
        generate_deploy_key("label-beta")
        labels = [k["label"] for k in list_deploy_keys()]
        assert "label-alpha" in labels
        assert "label-beta" in labels


# ---------------------------------------------------------------------------
# revoke_deploy_key
# ---------------------------------------------------------------------------


class TestRevokeDeployKey:
    def test_revoke_existing_key_returns_true(self):
        generate_deploy_key("revoke-me")
        result = revoke_deploy_key("revoke-me")
        assert result is True

    def test_revoke_nonexistent_key_returns_false(self):
        result = revoke_deploy_key("ghost-label")
        assert result is False

    def test_revoked_key_no_longer_in_list(self):
        generate_deploy_key("gone-key")
        revoke_deploy_key("gone-key")
        labels = [k["label"] for k in list_deploy_keys()]
        assert "gone-key" not in labels

    def test_revoking_one_key_leaves_others_intact(self):
        generate_deploy_key("keep-key")
        generate_deploy_key("delete-key")
        revoke_deploy_key("delete-key")
        labels = [k["label"] for k in list_deploy_keys()]
        assert "keep-key" in labels
        assert "delete-key" not in labels

    def test_revoked_key_fails_validation(self):
        key = generate_deploy_key("invalidated")
        revoke_deploy_key("invalidated")
        assert validate_deploy_key(key) is None
