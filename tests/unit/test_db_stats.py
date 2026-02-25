"""Tests for cli/core/db_stats.py — get_database_stats via SSH Docker exec."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

from cli.core.db_stats import get_database_stats


def _make_ssh(*responses: tuple[str, str, int]) -> MagicMock:
    """Return a mock SSHClient with sequential run() responses."""
    ssh = MagicMock()
    ssh.run = MagicMock(side_effect=list(responses))
    return ssh


# ---------------------------------------------------------------------------
# Postgres stats
# ---------------------------------------------------------------------------


class TestPostgresStats:
    def test_returns_disk_size(self):
        ssh = _make_ssh(
            ("  8192 kB  ", "", 0),  # pg_size_pretty
            ("  5  ", "", 0),  # pg_stat_activity count
            ("  16.2  ", "", 0),  # server_version
            ("  0:00:42  ", "", 0),  # uptime
        )
        result = get_database_stats(ssh, "mydb", "postgres")
        assert result["disk_size"] == "8192 kB"

    def test_returns_active_connections_as_int(self):
        ssh = _make_ssh(
            ("  8192 kB  ", "", 0),
            ("  5  ", "", 0),
            ("  16.2  ", "", 0),
            ("  0:00:42  ", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "postgres")
        assert result["active_connections"] == 5

    def test_returns_version(self):
        ssh = _make_ssh(
            ("  8192 kB  ", "", 0),
            ("  5  ", "", 0),
            ("  16.2  ", "", 0),
            ("  0:00:42  ", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "postgres")
        assert result["version"] == "16.2"

    def test_returns_uptime(self):
        ssh = _make_ssh(
            ("  8192 kB  ", "", 0),
            ("  5  ", "", 0),
            ("  16.2  ", "", 0),
            ("  0:00:42  ", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "postgres")
        assert result["uptime"] == "0:00:42"

    def test_disk_size_none_on_command_failure(self):
        ssh = _make_ssh(
            ("", "error", 1),  # disk size fails
            ("  3  ", "", 0),
            ("  16.2  ", "", 0),
            ("  1:00:00  ", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "postgres")
        assert result["disk_size"] is None

    def test_connections_none_on_command_failure(self):
        ssh = _make_ssh(
            ("  8192 kB  ", "", 0),
            ("", "error", 1),  # connections fails
            ("  16.2  ", "", 0),
            ("  1:00:00  ", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "postgres")
        assert result["active_connections"] is None

    def test_connections_none_on_non_numeric_output(self):
        ssh = _make_ssh(
            ("  8192 kB  ", "", 0),
            ("  not_a_number  ", "", 0),
            ("  16.2  ", "", 0),
            ("  1:00:00  ", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "postgres")
        assert result["active_connections"] is None

    def test_all_commands_fail_returns_none_values(self):
        ssh = _make_ssh(
            ("", "", 1),
            ("", "", 1),
            ("", "", 1),
            ("", "", 1),
        )
        result = get_database_stats(ssh, "mydb", "postgres")
        assert result["disk_size"] is None
        assert result["active_connections"] is None
        assert result["version"] is None
        assert result["uptime"] is None

    def test_uses_correct_container_name(self):
        ssh = _make_ssh(
            ("  1 kB  ", "", 0),
            ("  1  ", "", 0),
            ("  16  ", "", 0),
            ("  0:01:00  ", "", 0),
        )
        get_database_stats(ssh, "my-pg-db", "postgres")
        first_call = ssh.run.call_args_list[0][0][0]
        assert "infrakt-db-my-pg-db" in first_call


# ---------------------------------------------------------------------------
# MySQL stats
# ---------------------------------------------------------------------------


class TestMysqlStats:
    def test_returns_version(self):
        ssh = _make_ssh(
            ("8.0.33", "", 0),  # VERSION()
            ("Threads_connected\t4", "", 0),  # Threads_connected
            ("Uptime\t7200", "", 0),  # Uptime
        )
        result = get_database_stats(ssh, "mydb", "mysql")
        assert result["version"] == "8.0.33"

    def test_returns_active_connections(self):
        ssh = _make_ssh(
            ("8.0.33", "", 0),
            ("Threads_connected\t4", "", 0),
            ("Uptime\t7200", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "mysql")
        assert result["active_connections"] == 4

    def test_returns_uptime_formatted(self):
        # 7200 seconds = 2h 0m
        ssh = _make_ssh(
            ("8.0.33", "", 0),
            ("Threads_connected\t4", "", 0),
            ("Uptime\t7200", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "mysql")
        assert result["uptime"] == "2h 0m"

    def test_uptime_handles_partial_hour(self):
        # 3690 seconds = 1h 1m
        ssh = _make_ssh(
            ("8.0.33", "", 0),
            ("Threads_connected\t1", "", 0),
            ("Uptime\t3690", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "mysql")
        assert result["uptime"] == "1h 1m"

    def test_version_none_on_command_failure(self):
        ssh = _make_ssh(
            ("", "error", 1),
            ("Threads_connected\t1", "", 0),
            ("Uptime\t100", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "mysql")
        assert result["version"] is None

    def test_connections_none_on_bad_output(self):
        ssh = _make_ssh(
            ("8.0.33", "", 0),
            ("Threads_connected", "", 0),  # only one word (no count)
            ("Uptime\t100", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "mysql")
        assert result["active_connections"] is None

    def test_disk_size_is_none_for_mysql(self):
        ssh = _make_ssh(
            ("8.0.33", "", 0),
            ("Threads_connected\t1", "", 0),
            ("Uptime\t100", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "mysql")
        assert result["disk_size"] is None


# ---------------------------------------------------------------------------
# Redis stats
# ---------------------------------------------------------------------------


class TestRedisStats:
    REDIS_MEMORY = "used_memory_human:1.50M\nused_memory:1572864\n"
    REDIS_CLIENTS = "connected_clients:3\nblocked_clients:0\n"
    # NOTE: uptime_in_seconds must appear BEFORE redis_version in the server info
    # output because the source iterates lines and breaks on redis_version.
    REDIS_SERVER = "uptime_in_seconds:3661\nredis_version:7.0.8\narch_bits:64\n"

    def test_returns_disk_size_from_memory_info(self):
        ssh = _make_ssh(
            (self.REDIS_MEMORY, "", 0),
            (self.REDIS_CLIENTS, "", 0),
            (self.REDIS_SERVER, "", 0),
        )
        result = get_database_stats(ssh, "cache", "redis")
        assert result["disk_size"] == "1.50M"

    def test_returns_active_connections(self):
        ssh = _make_ssh(
            (self.REDIS_MEMORY, "", 0),
            (self.REDIS_CLIENTS, "", 0),
            (self.REDIS_SERVER, "", 0),
        )
        result = get_database_stats(ssh, "cache", "redis")
        assert result["active_connections"] == 3

    def test_returns_version(self):
        ssh = _make_ssh(
            (self.REDIS_MEMORY, "", 0),
            (self.REDIS_CLIENTS, "", 0),
            (self.REDIS_SERVER, "", 0),
        )
        result = get_database_stats(ssh, "cache", "redis")
        assert result["version"] == "7.0.8"

    def test_returns_uptime_formatted(self):
        # 3661 seconds = 1h 1m
        ssh = _make_ssh(
            (self.REDIS_MEMORY, "", 0),
            (self.REDIS_CLIENTS, "", 0),
            (self.REDIS_SERVER, "", 0),
        )
        result = get_database_stats(ssh, "cache", "redis")
        assert result["uptime"] == "1h 1m"

    def test_disk_size_none_when_memory_command_fails(self):
        ssh = _make_ssh(
            ("", "", 1),
            (self.REDIS_CLIENTS, "", 0),
            (self.REDIS_SERVER, "", 0),
        )
        result = get_database_stats(ssh, "cache", "redis")
        assert result["disk_size"] is None

    def test_connections_none_when_clients_command_fails(self):
        ssh = _make_ssh(
            (self.REDIS_MEMORY, "", 0),
            ("", "", 1),
            (self.REDIS_SERVER, "", 0),
        )
        result = get_database_stats(ssh, "cache", "redis")
        assert result["active_connections"] is None


# ---------------------------------------------------------------------------
# MongoDB stats
# ---------------------------------------------------------------------------


class TestMongoStats:
    def _make_server_status(self, connections: int = 2, uptime: int = 3600) -> str:
        return json.dumps(
            {
                "connections": {"current": connections, "available": 100},
                "uptime": uptime,
            }
        )

    def test_returns_version(self):
        ssh = _make_ssh(
            ("7.0.4", "", 0),
            (self._make_server_status(), "", 0),
        )
        result = get_database_stats(ssh, "mydb", "mongo")
        assert result["version"] == "7.0.4"

    def test_returns_active_connections(self):
        ssh = _make_ssh(
            ("7.0.4", "", 0),
            (self._make_server_status(connections=5), "", 0),
        )
        result = get_database_stats(ssh, "mydb", "mongo")
        assert result["active_connections"] == 5

    def test_returns_uptime_formatted(self):
        # 3600 seconds = 1h 0m
        ssh = _make_ssh(
            ("7.0.4", "", 0),
            (self._make_server_status(uptime=3600), "", 0),
        )
        result = get_database_stats(ssh, "mydb", "mongo")
        assert result["uptime"] == "1h 0m"

    def test_version_none_on_command_failure(self):
        ssh = _make_ssh(
            ("", "", 1),
            (self._make_server_status(), "", 0),
        )
        result = get_database_stats(ssh, "mydb", "mongo")
        assert result["version"] is None

    def test_connections_none_on_invalid_json(self):
        ssh = _make_ssh(
            ("7.0.4", "", 0),
            ("not valid json {{{", "", 0),
        )
        result = get_database_stats(ssh, "mydb", "mongo")
        assert result["active_connections"] is None

    def test_all_fields_none_when_all_commands_fail(self):
        ssh = _make_ssh(("", "", 1), ("", "", 1))
        result = get_database_stats(ssh, "mydb", "mongo")
        assert result["version"] is None
        assert result["active_connections"] is None
        assert result["uptime"] is None


# ---------------------------------------------------------------------------
# Unknown db_type
# ---------------------------------------------------------------------------


class TestUnknownDbType:
    def test_unknown_type_returns_all_none_stats(self):
        ssh = MagicMock()
        ssh.run = MagicMock(return_value=("", "", 0))
        result = get_database_stats(ssh, "mydb", "cassandra")
        assert result["disk_size"] is None
        assert result["active_connections"] is None
        assert result["version"] is None
        assert result["uptime"] is None

    def test_unknown_type_does_not_call_ssh(self):
        ssh = MagicMock()
        ssh.run = MagicMock()
        get_database_stats(ssh, "mydb", "unknown")
        ssh.run.assert_not_called()
