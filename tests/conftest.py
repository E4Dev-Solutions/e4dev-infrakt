from unittest.mock import MagicMock

import pytest

TEST_API_KEY = "test-api-key-for-tests"


@pytest.fixture(autouse=True)
def isolated_config(tmp_path, monkeypatch):
    """Redirect all infrakt config to a temp directory for test isolation."""
    monkeypatch.setattr("cli.core.config.INFRAKT_HOME", tmp_path)
    monkeypatch.setattr("cli.core.config.DB_PATH", tmp_path / "infrakt.db")
    monkeypatch.setattr("cli.core.config.KEYS_DIR", tmp_path / "keys")
    monkeypatch.setattr("cli.core.config.ENVS_DIR", tmp_path / "envs")
    monkeypatch.setattr("cli.core.config.MASTER_KEY_PATH", tmp_path / "master.key")
    (tmp_path / "keys").mkdir()
    (tmp_path / "envs").mkdir()

    # Write a known API key for test isolation
    api_key_path = tmp_path / "api_key.txt"
    api_key_path.write_text(TEST_API_KEY)
    api_key_path.chmod(0o600)

    # Reset engine so each test gets a fresh in-memory or temp DB
    import cli.core.database as db_mod

    db_mod._engine = None
    db_mod._SessionLocal = None

    yield tmp_path


@pytest.fixture
def mock_ssh():
    """Return a MagicMock SSHClient for testing without real SSH."""
    ssh = MagicMock()
    ssh.run.return_value = ("", "", 0)
    ssh.run_checked.return_value = ""
    ssh.test_connection.return_value = True
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    return ssh
