"""Tests for cli.core.backup module."""

from unittest.mock import MagicMock, patch

import pytest

from cli.core.backup import (
    _container_name,
    _extract_db_type,
    backup_database,
    restore_database,
)
from cli.core.exceptions import SSHConnectionError


def _make_app(
    name: str = "mydb", app_type: str = "db:postgres", parent_app_id: int | None = None
) -> MagicMock:
    app = MagicMock()
    app.name = name
    app.app_type = app_type
    app.parent_app_id = parent_app_id
    return app


class TestExtractDbType:
    def test_extracts_postgres(self):
        app = _make_app(app_type="db:postgres")
        assert _extract_db_type(app) == "postgres"

    def test_extracts_mysql(self):
        app = _make_app(app_type="db:mysql")
        assert _extract_db_type(app) == "mysql"

    def test_extracts_redis(self):
        app = _make_app(app_type="db:redis")
        assert _extract_db_type(app) == "redis"

    def test_extracts_mongo(self):
        app = _make_app(app_type="db:mongo")
        assert _extract_db_type(app) == "mongo"

    def test_raises_for_non_database(self):
        app = _make_app(app_type="git")
        with pytest.raises(ValueError, match="not a database"):
            _extract_db_type(app)


class TestContainerName:
    def test_returns_infrakt_db_prefix_for_standalone(self):
        app = _make_app(name="mydb")
        assert _container_name(app) == "infrakt-db-mydb"

    def test_returns_infrakt_prefix_for_template_child(self):
        app = _make_app(name="n8n-db", parent_app_id=1)
        assert _container_name(app) == "infrakt-n8n-db"


class TestBackupDatabase:
    def test_postgres_backup_runs_pg_dump(self, mock_ssh):
        app = _make_app("testdb", "db:postgres")
        with patch("cli.core.backup._timestamp", return_value="20260224_120000"):
            result = backup_database(mock_ssh, app)

        assert result == "/opt/infrakt/backups/testdb_20260224_120000.sql.gz"
        # Verify pg_dump command was called
        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("pg_dump" in c for c in calls)

    def test_mysql_backup_runs_mysqldump(self, mock_ssh):
        mock_ssh.run_checked.return_value = "secret123"  # password from printenv
        app = _make_app("testdb", "db:mysql")
        with patch("cli.core.backup._timestamp", return_value="20260224_120000"):
            result = backup_database(mock_ssh, app)

        assert result == "/opt/infrakt/backups/testdb_20260224_120000.sql.gz"
        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("mysqldump" in c for c in calls)

    def test_redis_backup_calls_bgsave(self, mock_ssh):
        app = _make_app("cache", "db:redis")
        with patch("cli.core.backup._timestamp", return_value="20260224_120000"):
            result = backup_database(mock_ssh, app)

        assert result == "/opt/infrakt/backups/cache_20260224_120000.rdb"
        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("BGSAVE" in c for c in calls)

    def test_mongo_backup_runs_mongodump(self, mock_ssh):
        mock_ssh.run_checked.return_value = "mongopass"
        app = _make_app("docdb", "db:mongo")
        with patch("cli.core.backup._timestamp", return_value="20260224_120000"):
            result = backup_database(mock_ssh, app)

        assert result == "/opt/infrakt/backups/docdb_20260224_120000.archive.gz"
        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("mongodump" in c for c in calls)

    def test_raises_for_unsupported_type(self, mock_ssh):
        app = _make_app("bad", "db:cockroach")
        with pytest.raises(ValueError, match="Unsupported"):
            backup_database(mock_ssh, app)

    def test_custom_backup_dir(self, mock_ssh):
        app = _make_app("testdb", "db:postgres")
        with patch("cli.core.backup._timestamp", return_value="20260224_120000"):
            result = backup_database(mock_ssh, app, backup_dir="/tmp/backups")

        assert result == "/tmp/backups/testdb_20260224_120000.sql.gz"


class TestRestoreDatabase:
    def test_postgres_restore_runs_psql(self, mock_ssh):
        mock_ssh.run.return_value = ("", "", 0)  # test -f succeeds
        app = _make_app("testdb", "db:postgres")
        restore_database(mock_ssh, app, "/opt/infrakt/backups/testdb.sql.gz")

        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("psql" in c for c in calls)

    def test_mysql_restore_runs_mysql(self, mock_ssh):
        mock_ssh.run.return_value = ("", "", 0)
        mock_ssh.run_checked.return_value = "secret123"
        app = _make_app("testdb", "db:mysql")
        restore_database(mock_ssh, app, "/opt/infrakt/backups/testdb.sql.gz")

        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("mysql" in c for c in calls)

    def test_redis_restore_copies_rdb(self, mock_ssh):
        mock_ssh.run.return_value = ("", "", 0)
        app = _make_app("cache", "db:redis")
        restore_database(mock_ssh, app, "/opt/infrakt/backups/cache.rdb")

        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("docker cp" in c for c in calls)

    def test_mongo_restore_runs_mongorestore(self, mock_ssh):
        mock_ssh.run.return_value = ("", "", 0)
        mock_ssh.run_checked.return_value = "mongopass"
        app = _make_app("docdb", "db:mongo")
        restore_database(mock_ssh, app, "/opt/infrakt/backups/docdb.archive.gz")

        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("mongorestore" in c for c in calls)

    def test_raises_when_backup_file_missing(self, mock_ssh):
        mock_ssh.run.return_value = ("", "", 1)  # test -f fails
        app = _make_app("testdb", "db:postgres")
        with pytest.raises(SSHConnectionError, match="not found"):
            restore_database(mock_ssh, app, "/opt/infrakt/backups/missing.sql.gz")

    def test_raises_for_unsupported_type(self, mock_ssh):
        mock_ssh.run.return_value = ("", "", 0)
        app = _make_app("bad", "db:cockroach")
        with pytest.raises(ValueError, match="Unsupported"):
            restore_database(mock_ssh, app, "/opt/infrakt/backups/bad.sql.gz")
