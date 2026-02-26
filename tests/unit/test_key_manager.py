"""Tests for cli/core/key_manager.py — SSH key generation, import, and deployment.

Uses real cryptography operations (Ed25519 is fast) instead of mocking,
which makes the tests more reliable across paramiko/cryptography versions.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

import cli.core.key_manager as km_mod
from cli.core.exceptions import InfraktError, SSHConnectionError
from cli.core.key_manager import (
    deploy_key_to_server,
    generate_key,
    get_fingerprint,
    get_public_key,
    import_key,
    remove_key_files,
)


@pytest.fixture(autouse=True)
def patch_keys_dir(isolated_config, monkeypatch):
    """Redirect KEYS_DIR inside key_manager to the isolated temp directory."""
    keys_dir = isolated_config / "keys"
    keys_dir.mkdir(exist_ok=True)
    monkeypatch.setattr(km_mod, "KEYS_DIR", keys_dir)
    return keys_dir


# ---------------------------------------------------------------------------
# generate_key
# ---------------------------------------------------------------------------


class TestGenerateKey:
    def test_returns_tuple_of_path_and_fingerprint(self, isolated_config, patch_keys_dir):
        private_path, fingerprint = generate_key("test-key")
        assert isinstance(private_path, Path)
        assert isinstance(fingerprint, str)

    def test_private_key_file_path_is_in_keys_dir(self, isolated_config, patch_keys_dir):
        private_path, _ = generate_key("my-key")
        assert private_path.parent == patch_keys_dir

    def test_public_key_file_is_created(self, isolated_config, patch_keys_dir):
        generate_key("my-key")
        pub_path = patch_keys_dir / "my-key.pub"
        assert pub_path.exists()

    def test_fingerprint_starts_with_sha256_prefix(self, isolated_config, patch_keys_dir):
        _, fingerprint = generate_key("my-key")
        assert fingerprint.startswith("SHA256:")

    def test_public_key_content_has_expected_format(self, isolated_config, patch_keys_dir):
        generate_key("format-key")
        pub_content = (patch_keys_dir / "format-key.pub").read_text()
        assert pub_content.startswith("ssh-ed25519 ")

    def test_private_key_file_is_written(self, isolated_config, patch_keys_dir):
        generate_key("write-key")
        assert (patch_keys_dir / "write-key").exists()

    def test_different_names_produce_different_paths(self, isolated_config, patch_keys_dir):
        path1, _ = generate_key("key-alpha")
        path2, _ = generate_key("key-beta")
        assert path1 != path2

    def test_private_key_has_correct_permissions(self, isolated_config, patch_keys_dir):
        generate_key("perm-key")
        mode = (patch_keys_dir / "perm-key").stat().st_mode & 0o777
        assert mode == 0o600


# ---------------------------------------------------------------------------
# import_key
# ---------------------------------------------------------------------------


class TestImportKey:
    def _generate_source_key(self, tmp_path: Path) -> Path:
        """Generate a real Ed25519 key to use as import source."""
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key = Ed25519PrivateKey.generate()
        from cryptography.hazmat.primitives import serialization

        source = tmp_path / "source_key"
        source.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.OpenSSH,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        return source

    def test_import_existing_key_returns_path_and_fingerprint(self, isolated_config, tmp_path):
        source_path = self._generate_source_key(tmp_path)
        private_path, fingerprint = import_key("imported-key", source_path)
        assert isinstance(private_path, Path)
        assert fingerprint.startswith("SHA256:")

    def test_import_copies_key_to_keys_dir(self, isolated_config, patch_keys_dir, tmp_path):
        source_path = self._generate_source_key(tmp_path)
        import_key("copied-key", source_path)
        expected_path = patch_keys_dir / "copied-key"
        assert expected_path.exists()

    def test_import_also_creates_public_key_file(self, isolated_config, patch_keys_dir, tmp_path):
        source_path = self._generate_source_key(tmp_path)
        import_key("pub-key", source_path)
        pub_path = patch_keys_dir / "pub-key.pub"
        assert pub_path.exists()

    def test_import_public_key_starts_with_ssh_ed25519(
        self, isolated_config, patch_keys_dir, tmp_path
    ):
        source_path = self._generate_source_key(tmp_path)
        import_key("content-key", source_path)
        pub_content = (patch_keys_dir / "content-key.pub").read_text()
        assert pub_content.startswith("ssh-ed25519 ")

    def test_import_nonexistent_file_raises_infrakt_error(self, isolated_config, tmp_path):
        missing_path = tmp_path / "does_not_exist"
        with pytest.raises(InfraktError, match="Failed to import"):
            import_key("bad-key", missing_path)

    def test_import_bad_key_raises_infrakt_error(self, isolated_config, tmp_path):
        bad_key_path = tmp_path / "bad_key"
        bad_key_path.write_text("not a valid key")
        with pytest.raises(InfraktError, match="Failed to import"):
            import_key("bad-key", bad_key_path)


# ---------------------------------------------------------------------------
# get_fingerprint
# ---------------------------------------------------------------------------


class TestGetFingerprint:
    def test_returns_sha256_fingerprint(self, isolated_config, patch_keys_dir):
        private_path, _ = generate_key("fp-key")
        fingerprint = get_fingerprint(private_path)
        assert fingerprint.startswith("SHA256:")

    def test_fingerprint_is_deterministic_for_same_key(self, isolated_config, patch_keys_dir):
        private_path, _ = generate_key("det-key")
        fp1 = get_fingerprint(private_path)
        fp2 = get_fingerprint(private_path)
        assert fp1 == fp2

    def test_failure_raises_infrakt_error(self, isolated_config, tmp_path):
        with pytest.raises(InfraktError, match="Failed to read key fingerprint"):
            get_fingerprint(tmp_path / "no_such_key")

    def test_fingerprint_format_sha256_colon_base64(self, isolated_config, patch_keys_dir):
        private_path, _ = generate_key("fmt-key")
        fingerprint = get_fingerprint(private_path)
        parts = fingerprint.split(":", 1)
        assert len(parts) == 2
        assert parts[0] == "SHA256"
        assert len(parts[1]) > 10


# ---------------------------------------------------------------------------
# get_public_key
# ---------------------------------------------------------------------------


class TestGetPublicKey:
    def test_returns_ssh_ed25519_string(self, isolated_config, patch_keys_dir):
        private_path, _ = generate_key("pub-key")
        pub_string = get_public_key(private_path)
        assert pub_string.startswith("ssh-ed25519 ")

    def test_returns_two_space_separated_fields(self, isolated_config, patch_keys_dir):
        private_path, _ = generate_key("two-field-key")
        pub_string = get_public_key(private_path)
        parts = pub_string.strip().split()
        assert len(parts) == 2

    def test_failure_raises_infrakt_error(self, isolated_config, tmp_path):
        with pytest.raises(InfraktError, match="Failed to read public key"):
            get_public_key(tmp_path / "missing")


# ---------------------------------------------------------------------------
# remove_key_files
# ---------------------------------------------------------------------------


class TestRemoveKeyFiles:
    def test_removes_private_and_public_key_files(self, isolated_config, patch_keys_dir):
        private_path = patch_keys_dir / "del-key"
        pub_path = patch_keys_dir / "del-key.pub"
        private_path.write_text("fake-private-key")
        pub_path.write_text("ssh-ed25519 AAAA fake")

        assert private_path.exists()
        assert pub_path.exists()

        remove_key_files("del-key")
        assert not private_path.exists()
        assert not pub_path.exists()

    def test_remove_nonexistent_key_does_not_raise(self, isolated_config, patch_keys_dir):
        remove_key_files("ghost-key")

    def test_remove_only_private_key_when_pub_missing(self, isolated_config, patch_keys_dir):
        private_path = patch_keys_dir / "priv-only"
        private_path.write_text("fake")
        remove_key_files("priv-only")
        assert not private_path.exists()


# ---------------------------------------------------------------------------
# deploy_key_to_server
# ---------------------------------------------------------------------------


class TestDeployKeyToServer:
    def test_mkdir_ssh_dir_is_called(self, isolated_config):
        ssh = MagicMock()
        ssh.run_checked = MagicMock(return_value="")
        deploy_key_to_server(ssh, "ssh-ed25519 AAAAC3 user@host")
        ssh.run_checked.assert_any_call("mkdir -p ~/.ssh")

    def test_key_is_appended_to_authorized_keys(self, isolated_config):
        ssh = MagicMock()
        ssh.run_checked = MagicMock(side_effect=["", "", "", ""])
        deploy_key_to_server(ssh, "ssh-ed25519 AAAAC3 user@host")
        calls_text = " ".join(str(c) for c in ssh.run_checked.call_args_list)
        assert "authorized_keys" in calls_text

    def test_key_not_added_when_already_present(self, isolated_config):
        public_key = "ssh-ed25519 AAAAC3 user@host"
        ssh = MagicMock()
        ssh.run_checked = MagicMock(side_effect=["", public_key])
        deploy_key_to_server(ssh, public_key)
        assert ssh.run_checked.call_count == 2

    def test_permissions_are_set_after_adding_key(self, isolated_config):
        ssh = MagicMock()
        ssh.run_checked = MagicMock(side_effect=["", "", "", ""])
        deploy_key_to_server(ssh, "ssh-ed25519 AAAAC3 user@host")
        calls_text = " ".join(str(c) for c in ssh.run_checked.call_args_list)
        assert "chmod 600" in calls_text

    def test_ssh_error_raises_ssh_connection_error(self, isolated_config):
        ssh = MagicMock()
        ssh.run_checked = MagicMock(side_effect=SSHConnectionError("connection refused"))
        with pytest.raises(SSHConnectionError, match="Failed to deploy key"):
            deploy_key_to_server(ssh, "ssh-ed25519 AAAAC3 user@host")
