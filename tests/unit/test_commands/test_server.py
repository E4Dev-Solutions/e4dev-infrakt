from unittest.mock import patch

import pytest
from click.testing import CliRunner

from cli.core.database import init_db
from cli.main import cli


@pytest.fixture
def runner():
    return CliRunner()


def test_server_add(runner, isolated_config):
    with patch("cli.commands.server.SSHClient") as mock_cls:
        mock_cls.return_value.test_connection.return_value = True
        result = runner.invoke(cli, [
            "server", "add",
            "--name", "test-srv",
            "--host", "1.2.3.4",
            "--user", "root",
        ])
    assert result.exit_code == 0
    assert "test-srv" in result.output


def test_server_list_empty(runner, isolated_config):
    result = runner.invoke(cli, ["server", "list"])
    assert result.exit_code == 0
    assert "No servers" in result.output


def test_server_list_with_servers(runner, isolated_config):
    with patch("cli.commands.server.SSHClient") as mock_cls:
        mock_cls.return_value.test_connection.return_value = True
        runner.invoke(cli, [
            "server", "add", "--name", "srv1", "--host", "1.1.1.1", "--user", "root",
        ])

    result = runner.invoke(cli, ["server", "list"])
    assert result.exit_code == 0
    assert "srv1" in result.output


def test_server_remove(runner, isolated_config):
    with patch("cli.commands.server.SSHClient") as mock_cls:
        mock_cls.return_value.test_connection.return_value = True
        runner.invoke(cli, [
            "server", "add", "--name", "del-me", "--host", "2.2.2.2", "--user", "root",
        ])

    result = runner.invoke(cli, ["server", "remove", "del-me", "--force"])
    assert result.exit_code == 0
    assert "removed" in result.output
