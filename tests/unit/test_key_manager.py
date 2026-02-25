"""Tests for cli/core/key_manager.py — SSH key generation, import, and deployment.

Note: key_manager.py imports KEYS_DIR at module level from cli.core.config.
All tests that touch the filesystem also patch cli.core.key_manager.KEYS_DIR
to ensure isolation. generate_key uses paramiko.Ed25519Key.generate which was
removed in paramiko 4.x; those tests mock the paramiko module.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

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


def _make_mock_paramiko_key(
    name: str = "ssh-ed25519",
    b64: str = "AAAAC3NzaC1lZDI1NTE5AAAAIFakeKeyForTesting==",
) -> MagicMock:
    """Return a MagicMock that behaves like a paramiko PKey."""
    key = MagicMock()
    key.get_name.return_value = name
    key.get_base64.return_value = b64
    key.write_private_key_file = MagicMock()
    return key


def _mock_write_private_key_file(path: str, password=None) -> None:
    """Side-effect for write_private_key_file that creates the actual file."""
    Path(path).write_text("MOCK PRIVATE KEY")
    Path(path).chmod(0o600)


# ---------------------------------------------------------------------------
# generate_key — mocks paramiko.Ed25519Key.generate (removed in paramiko 4.x)
# ---------------------------------------------------------------------------


class TestGenerateKey:
    def test_returns_tuple_of_path_and_fingerprint(self, isolated_config, patch_keys_dir):
        mock_key = _make_mock_paramiko_key()
        mock_key.write_private_key_file.side_effect = _mock_write_private_key_file
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.Ed25519Key.generate.return_value = mock_key
            private_path, fingerprint = generate_key("test-key")
        assert isinstance(private_path, Path)
        assert isinstance(fingerprint, str)

    def test_private_key_file_path_is_in_keys_dir(self, isolated_config, patch_keys_dir):
        mock_key = _make_mock_paramiko_key()
        mock_key.write_private_key_file.side_effect = _mock_write_private_key_file
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.Ed25519Key.generate.return_value = mock_key
            private_path, _ = generate_key("my-key")
        assert private_path.parent == patch_keys_dir

    def test_public_key_file_is_created(self, isolated_config, patch_keys_dir):
        mock_key = _make_mock_paramiko_key()
        mock_key.write_private_key_file.side_effect = _mock_write_private_key_file
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.Ed25519Key.generate.return_value = mock_key
            generate_key("my-key")
        pub_path = patch_keys_dir / "my-key.pub"
        assert pub_path.exists()

    def test_fingerprint_starts_with_sha256_prefix(self, isolated_config, patch_keys_dir):
        mock_key = _make_mock_paramiko_key()
        mock_key.write_private_key_file.side_effect = _mock_write_private_key_file
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.Ed25519Key.generate.return_value = mock_key
            _, fingerprint = generate_key("my-key")
        assert fingerprint.startswith("SHA256:")

    def test_public_key_content_has_expected_format(self, isolated_config, patch_keys_dir):
        mock_key = _make_mock_paramiko_key()
        mock_key.write_private_key_file.side_effect = _mock_write_private_key_file
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.Ed25519Key.generate.return_value = mock_key
            generate_key("format-key")
        pub_content = (patch_keys_dir / "format-key.pub").read_text()
        assert pub_content.startswith("ssh-ed25519 ")

    def test_write_private_key_file_is_called(self, isolated_config, patch_keys_dir):
        mock_key = _make_mock_paramiko_key()
        mock_key.write_private_key_file.side_effect = _mock_write_private_key_file
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.Ed25519Key.generate.return_value = mock_key
            generate_key("write-key")
        mock_key.write_private_key_file.assert_called_once()

    def test_different_names_produce_different_paths(self, isolated_config, patch_keys_dir):
        mock_key1 = _make_mock_paramiko_key()
        mock_key1.write_private_key_file.side_effect = _mock_write_private_key_file
        mock_key2 = _make_mock_paramiko_key()
        mock_key2.write_private_key_file.side_effect = _mock_write_private_key_file
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.Ed25519Key.generate.return_value = mock_key1
            path1, _ = generate_key("key-alpha")
            mock_paramiko.Ed25519Key.generate.return_value = mock_key2
            path2, _ = generate_key("key-beta")
        assert path1 != path2

    def test_get_name_and_get_base64_are_called_for_public_key(
        self, isolated_config, patch_keys_dir
    ):
        mock_key = _make_mock_paramiko_key()
        mock_key.write_private_key_file.side_effect = _mock_write_private_key_file
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.Ed25519Key.generate.return_value = mock_key
            generate_key("key-pub-check")
        mock_key.get_name.assert_called()
        mock_key.get_base64.assert_called()


# ---------------------------------------------------------------------------
# import_key — mocks paramiko.PKey.from_private_key_file (changed in 4.x)
# ---------------------------------------------------------------------------


class TestImportKey:
    def test_import_existing_key_returns_path_and_fingerprint(self, isolated_config, tmp_path):
        source_path = tmp_path / "source_key"
        source_path.write_text("fake-pem-key-content")

        mock_key = _make_mock_paramiko_key()
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.return_value = mock_key
            private_path, fingerprint = import_key("imported-key", source_path)

        assert isinstance(private_path, Path)
        assert fingerprint.startswith("SHA256:")

    def test_import_copies_key_to_keys_dir(self, isolated_config, patch_keys_dir, tmp_path):
        source_path = tmp_path / "source_key"
        source_path.write_text("fake-pem-key-content")

        mock_key = _make_mock_paramiko_key()
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.return_value = mock_key
            import_key("copied-key", source_path)

        expected_path = patch_keys_dir / "copied-key"
        assert expected_path.exists()

    def test_import_also_creates_public_key_file(self, isolated_config, patch_keys_dir, tmp_path):
        source_path = tmp_path / "source_key"
        source_path.write_text("fake-pem-key-content")

        mock_key = _make_mock_paramiko_key()
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.return_value = mock_key
            import_key("pub-key", source_path)

        pub_path = patch_keys_dir / "pub-key.pub"
        assert pub_path.exists()

    def test_import_public_key_starts_with_ssh_ed25519(
        self, isolated_config, patch_keys_dir, tmp_path
    ):
        source_path = tmp_path / "source_key"
        source_path.write_text("fake-pem-key-content")

        mock_key = _make_mock_paramiko_key()
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.return_value = mock_key
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
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.side_effect = Exception("bad key format")
            with pytest.raises(InfraktError, match="Failed to import"):
                import_key("bad-key", bad_key_path)


# ---------------------------------------------------------------------------
# get_fingerprint
# ---------------------------------------------------------------------------


class TestGetFingerprint:
    def test_returns_sha256_fingerprint(self, isolated_config, tmp_path):
        key_path = tmp_path / "fp_key"
        key_path.write_text("fake-pem-content")
        mock_key = _make_mock_paramiko_key()
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.return_value = mock_key
            fingerprint = get_fingerprint(key_path)
        assert fingerprint.startswith("SHA256:")

    def test_fingerprint_is_deterministic_for_same_key(self, isolated_config, tmp_path):
        key_path = tmp_path / "det_key"
        key_path.write_text("fake-pem-content")
        mock_key = _make_mock_paramiko_key()
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.return_value = mock_key
            fp1 = get_fingerprint(key_path)
            fp2 = get_fingerprint(key_path)
        assert fp1 == fp2

    def test_failure_raises_infrakt_error(self, isolated_config, tmp_path):
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.side_effect = Exception("not found")
            with pytest.raises(InfraktError, match="Failed to read key fingerprint"):
                get_fingerprint(tmp_path / "no_such_key")

    def test_fingerprint_format_sha256_colon_base64(self, isolated_config, tmp_path):
        key_path = tmp_path / "fmt_key"
        key_path.write_text("fake-pem-content")
        mock_key = _make_mock_paramiko_key()
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.return_value = mock_key
            fingerprint = get_fingerprint(key_path)
        parts = fingerprint.split(":", 1)
        assert len(parts) == 2
        assert parts[0] == "SHA256"
        assert len(parts[1]) > 10


# ---------------------------------------------------------------------------
# get_public_key
# ---------------------------------------------------------------------------


class TestGetPublicKey:
    def test_returns_ssh_ed25519_string(self, isolated_config, tmp_path):
        key_path = tmp_path / "pub_key"
        key_path.write_text("fake-pem-content")
        mock_key = _make_mock_paramiko_key()
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.return_value = mock_key
            pub_string = get_public_key(key_path)
        assert pub_string.startswith("ssh-ed25519 ")

    def test_returns_two_space_separated_fields(self, isolated_config, tmp_path):
        key_path = tmp_path / "two_field_key"
        key_path.write_text("fake-pem-content")
        mock_key = _make_mock_paramiko_key()
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.return_value = mock_key
            pub_string = get_public_key(key_path)
        parts = pub_string.strip().split()
        assert len(parts) == 2

    def test_failure_raises_infrakt_error(self, isolated_config, tmp_path):
        with patch("cli.core.key_manager.paramiko") as mock_paramiko:
            mock_paramiko.PKey.from_private_key_file.side_effect = Exception("read error")
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
        # Should silently succeed when files don't exist
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
        # Calls in order: mkdir, cat (returns empty), echo append, chmod
        ssh.run_checked = MagicMock(side_effect=["", "", "", ""])
        deploy_key_to_server(ssh, "ssh-ed25519 AAAAC3 user@host")
        calls_text = " ".join(str(c) for c in ssh.run_checked.call_args_list)
        assert "authorized_keys" in calls_text

    def test_key_not_added_when_already_present(self, isolated_config):
        public_key = "ssh-ed25519 AAAAC3 user@host"
        ssh = MagicMock()
        # cat returns the key already in authorized_keys
        ssh.run_checked = MagicMock(side_effect=["", public_key])
        deploy_key_to_server(ssh, public_key)
        # Only mkdir and cat should be called; echo must NOT be called
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
