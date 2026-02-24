"""Tests for the 'env' CLI command group (set, get, list, delete)."""


import pytest
from click.testing import CliRunner

from cli.core.database import get_session, init_db
from cli.main import cli
from cli.models.app import App
from cli.models.server import Server


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def patch_env_module_paths(isolated_config, monkeypatch):
    """
    cli.commands.env does 'from cli.core.config import ENVS_DIR' — a name binding
    that captures the value at import time.  The conftest isolated_config fixture
    patches cli.core.config.ENVS_DIR, but that does NOT update the already-bound
    name inside cli.commands.env.  We must patch it there directly.
    """
    monkeypatch.setattr("cli.commands.env.ENVS_DIR", isolated_config / "envs")


def _seed_app(isolated_config, server_name="srv", app_name="my-app"):
    """Create a server + app in the isolated DB, return the app name."""
    init_db()
    with get_session() as session:
        srv = Server(name=server_name, host="1.2.3.4", user="root", port=22, status="active")
        session.add(srv)
        session.flush()
        app_obj = App(name=app_name, server_id=srv.id, port=3000, app_type="git", status="stopped")
        session.add(app_obj)
    return app_name


# ---------------------------------------------------------------------------
# env set
# ---------------------------------------------------------------------------

class TestEnvSet:
    def test_set_single_variable_succeeds(self, runner, isolated_config):
        _seed_app(isolated_config)
        result = runner.invoke(cli, ["env", "set", "my-app", "FOO=bar"])
        assert result.exit_code == 0
        assert "1" in result.output  # "Set 1 variable(s)"

    def test_set_multiple_variables_at_once(self, runner, isolated_config):
        _seed_app(isolated_config)
        result = runner.invoke(cli, ["env", "set", "my-app", "A=1", "B=2", "C=3"])
        assert result.exit_code == 0
        assert "3" in result.output

    def test_set_stores_encrypted_value(self, runner, isolated_config):
        _seed_app(isolated_config)
        runner.invoke(cli, ["env", "set", "my-app", "SECRET=mysecretvalue"])
        # The value stored on disk should NOT be the plaintext
        import json
        # Find the env file
        files = list(isolated_config.joinpath("envs").glob("*.json"))
        assert len(files) == 1
        data = json.loads(files[0].read_text())
        assert "SECRET" in data
        assert data["SECRET"] != "mysecretvalue"  # must be encrypted

    def test_set_fails_when_app_not_found(self, runner, isolated_config):
        result = runner.invoke(cli, ["env", "set", "ghost-app", "X=1"])
        assert result.exit_code != 0

    def test_set_fails_on_invalid_key_value_format(self, runner, isolated_config):
        _seed_app(isolated_config)
        result = runner.invoke(cli, ["env", "set", "my-app", "NOEQUALS"])
        assert result.exit_code != 0
        assert "Invalid format" in result.output or "KEY=VALUE" in result.output

    def test_set_allows_value_containing_equals_sign(self, runner, isolated_config):
        _seed_app(isolated_config)
        # Value itself contains "=" — should only split on the first "="
        result = runner.invoke(cli, ["env", "set", "my-app", "CONN=user=pass@host"])
        assert result.exit_code == 0
        # Retrieve and confirm the full value is preserved
        get_result = runner.invoke(cli, ["env", "get", "my-app", "CONN"])
        assert "user=pass@host" in get_result.output

    def test_set_overwrites_existing_variable(self, runner, isolated_config):
        _seed_app(isolated_config)
        runner.invoke(cli, ["env", "set", "my-app", "KEY=first"])
        runner.invoke(cli, ["env", "set", "my-app", "KEY=second"])
        result = runner.invoke(cli, ["env", "get", "my-app", "KEY"])
        assert "second" in result.output
        assert "first" not in result.output


# ---------------------------------------------------------------------------
# env get
# ---------------------------------------------------------------------------

class TestEnvGet:
    def test_get_returns_decrypted_value(self, runner, isolated_config):
        _seed_app(isolated_config)
        runner.invoke(cli, ["env", "set", "my-app", "DB_URL=postgres://localhost/db"])
        result = runner.invoke(cli, ["env", "get", "my-app", "DB_URL"])
        assert result.exit_code == 0
        assert "postgres://localhost/db" in result.output

    def test_get_fails_when_variable_not_set(self, runner, isolated_config):
        _seed_app(isolated_config)
        result = runner.invoke(cli, ["env", "get", "my-app", "MISSING_VAR"])
        assert result.exit_code != 0
        assert "MISSING_VAR" in result.output

    def test_get_fails_when_app_not_found(self, runner, isolated_config):
        result = runner.invoke(cli, ["env", "get", "ghost-app", "KEY"])
        assert result.exit_code != 0

    def test_get_returns_empty_string_value_correctly(self, runner, isolated_config):
        _seed_app(isolated_config)
        runner.invoke(cli, ["env", "set", "my-app", "EMPTY="])
        result = runner.invoke(cli, ["env", "get", "my-app", "EMPTY"])
        assert result.exit_code == 0


# ---------------------------------------------------------------------------
# env list
# ---------------------------------------------------------------------------

class TestEnvList:
    def test_list_shows_no_vars_message_when_empty(self, runner, isolated_config):
        _seed_app(isolated_config)
        result = runner.invoke(cli, ["env", "list", "my-app"])
        assert result.exit_code == 0
        assert "No environment variables" in result.output

    def test_list_shows_key_names_after_setting_vars(self, runner, isolated_config):
        _seed_app(isolated_config)
        runner.invoke(cli, ["env", "set", "my-app", "ALPHA=1", "BETA=2"])
        result = runner.invoke(cli, ["env", "list", "my-app"])
        assert result.exit_code == 0
        assert "ALPHA" in result.output
        assert "BETA" in result.output

    def test_list_masks_values_by_default(self, runner, isolated_config):
        _seed_app(isolated_config)
        runner.invoke(cli, ["env", "set", "my-app", "PWD=hunter2"])
        result = runner.invoke(cli, ["env", "list", "my-app"])
        assert result.exit_code == 0
        assert "hunter2" not in result.output
        assert "••" in result.output  # masked placeholder

    def test_list_with_show_values_flag_reveals_values(self, runner, isolated_config):
        _seed_app(isolated_config)
        runner.invoke(cli, ["env", "set", "my-app", "PWD=hunter2"])
        result = runner.invoke(cli, ["env", "list", "my-app", "--show-values"])
        assert result.exit_code == 0
        assert "hunter2" in result.output

    def test_list_fails_when_app_not_found(self, runner, isolated_config):
        result = runner.invoke(cli, ["env", "list", "ghost-app"])
        assert result.exit_code != 0

    def test_list_displays_multiple_vars_in_sorted_order(self, runner, isolated_config):
        _seed_app(isolated_config)
        runner.invoke(cli, ["env", "set", "my-app", "ZEBRA=z", "APPLE=a", "MANGO=m"])
        result = runner.invoke(cli, ["env", "list", "my-app"])
        # All keys should appear
        assert "APPLE" in result.output
        assert "MANGO" in result.output
        assert "ZEBRA" in result.output
        # APPLE should appear before ZEBRA in sorted output
        assert result.output.index("APPLE") < result.output.index("ZEBRA")


# ---------------------------------------------------------------------------
# env delete
# ---------------------------------------------------------------------------

class TestEnvDelete:
    def test_delete_removes_existing_variable(self, runner, isolated_config):
        _seed_app(isolated_config)
        runner.invoke(cli, ["env", "set", "my-app", "TO_DELETE=gone"])
        result = runner.invoke(cli, ["env", "delete", "my-app", "TO_DELETE"])
        assert result.exit_code == 0
        # Confirm it is gone
        get_result = runner.invoke(cli, ["env", "get", "my-app", "TO_DELETE"])
        assert get_result.exit_code != 0

    def test_delete_success_message_includes_key_name(self, runner, isolated_config):
        _seed_app(isolated_config)
        runner.invoke(cli, ["env", "set", "my-app", "MY_KEY=val"])
        result = runner.invoke(cli, ["env", "delete", "my-app", "MY_KEY"])
        assert "MY_KEY" in result.output

    def test_delete_fails_when_variable_not_set(self, runner, isolated_config):
        _seed_app(isolated_config)
        result = runner.invoke(cli, ["env", "delete", "my-app", "NONEXISTENT"])
        assert result.exit_code != 0
        assert "NONEXISTENT" in result.output

    def test_delete_fails_when_app_not_found(self, runner, isolated_config):
        result = runner.invoke(cli, ["env", "delete", "ghost-app", "KEY"])
        assert result.exit_code != 0

    def test_delete_does_not_affect_other_variables(self, runner, isolated_config):
        _seed_app(isolated_config)
        runner.invoke(cli, ["env", "set", "my-app", "KEEP=kept", "REMOVE=gone"])
        runner.invoke(cli, ["env", "delete", "my-app", "REMOVE"])
        result = runner.invoke(cli, ["env", "get", "my-app", "KEEP"])
        assert result.exit_code == 0
        assert "kept" in result.output
