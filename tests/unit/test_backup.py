"""Tests for cli.core.backup module."""

from unittest.mock import MagicMock, patch

import pytest

from cli.core.backup import (
    _container_name,
    _extract_db_type,
    _resolve_container_name,
    backup_database,
    restore_database,
)
from cli.core.exceptions import SSHConnectionError


def _make_app(
    name: str = "mydb",
    app_type: str = "db:postgres",
    parent_app_id: int | None = None,
    backup_id: str = "a1b2c3d4",
) -> MagicMock:
    app = MagicMock()
    app.name = name
    app.app_type = app_type
    app.parent_app_id = parent_app_id
    app.backup_id = backup_id
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


class TestResolveContainerName:
    def test_returns_expected_name_when_found(self, mock_ssh):
        app = _make_app(name="n8n-db", parent_app_id=1)
        mock_ssh.run.return_value = ("", "", 0)
        assert _resolve_container_name(mock_ssh, app) == "infrakt-n8n-db"

    def test_falls_back_to_suffix_for_repo_embedded_db(self, mock_ssh):
        app = _make_app(name="myapp-postgres", parent_app_id=1)
        # First inspect (expected name) fails, second (with -1) succeeds
        mock_ssh.run.side_effect = [("", "", 1), ("", "", 0)]
        assert _resolve_container_name(mock_ssh, app) == "infrakt-myapp-postgres-1"

    def test_returns_expected_when_neither_found(self, mock_ssh):
        app = _make_app(name="myapp-postgres", parent_app_id=1)
        mock_ssh.run.side_effect = [("", "", 1), ("", "", 1)]
        assert _resolve_container_name(mock_ssh, app) == "infrakt-myapp-postgres"


class TestBackupDatabase:
    def test_postgres_backup_runs_pg_dump_custom_format(self, mock_ssh):
        app = _make_app("testdb", "db:postgres")
        with patch("cli.core.backup._timestamp", return_value="20260224_120000"):
            result = backup_database(mock_ssh, app, server_name="prod-1")

        expected = "/opt/infrakt/backups/prod-1_testdb_postgres_a1b2c3d4_20260224_120000.dump"
        assert result == expected
        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("pg_dump -Fc" in c for c in calls)

    def test_mysql_backup_runs_mysqldump(self, mock_ssh):
        mock_ssh.run_checked.return_value = "secret123"  # password from printenv
        app = _make_app("testdb", "db:mysql")
        with patch("cli.core.backup._timestamp", return_value="20260224_120000"):
            result = backup_database(mock_ssh, app, server_name="prod-1")

        assert result == "/opt/infrakt/backups/prod-1_testdb_mysql_a1b2c3d4_20260224_120000.sql.gz"
        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("mysqldump" in c for c in calls)

    def test_redis_backup_calls_bgsave(self, mock_ssh):
        app = _make_app("cache", "db:redis")
        with patch("cli.core.backup._timestamp", return_value="20260224_120000"):
            result = backup_database(mock_ssh, app, server_name="prod-1")

        assert result == "/opt/infrakt/backups/prod-1_cache_redis_a1b2c3d4_20260224_120000.rdb"
        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("BGSAVE" in c for c in calls)

    def test_mongo_backup_runs_mongodump(self, mock_ssh):
        mock_ssh.run_checked.return_value = "mongopass"
        app = _make_app("docdb", "db:mongo")
        with patch("cli.core.backup._timestamp", return_value="20260224_120000"):
            result = backup_database(mock_ssh, app, server_name="prod-1")

        expected = "/opt/infrakt/backups/prod-1_docdb_mongo_a1b2c3d4_20260224_120000.archive.gz"
        assert result == expected
        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("mongodump" in c for c in calls)

    def test_raises_for_unsupported_type(self, mock_ssh):
        app = _make_app("bad", "db:cockroach")
        with pytest.raises(ValueError, match="Unsupported"):
            backup_database(mock_ssh, app)

    def test_custom_backup_dir(self, mock_ssh):
        app = _make_app("testdb", "db:postgres")
        with patch("cli.core.backup._timestamp", return_value="20260224_120000"):
            result = backup_database(mock_ssh, app, server_name="prod-1", backup_dir="/tmp/backups")

        assert result == "/tmp/backups/prod-1_testdb_postgres_a1b2c3d4_20260224_120000.dump"


class TestRestoreDatabase:
    def test_postgres_restore_uses_pg_restore_for_dump(self, mock_ssh):
        # docker inspect (resolve), test -f, head -c 5 (magic bytes)
        mock_ssh.run.side_effect = [("", "", 0), ("", "", 0), ("PGDMP", "", 0)]
        app = _make_app("testdb", "db:postgres")
        restore_database(mock_ssh, app, "/opt/infrakt/backups/testdb.dump")

        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("pg_restore" in c for c in calls)
        assert any("--clean" in c for c in calls)
        assert any("--if-exists" in c for c in calls)

    def test_postgres_restore_legacy_sql_gz_uses_psql(self, mock_ssh):
        """Old .sql.gz backups with plain SQL should restore via gunzip | psql."""
        # docker inspect (resolve), test -f, gunzip magic check (not PGDMP)
        mock_ssh.run.side_effect = [("", "", 0), ("", "", 0), ("-- SQL", "", 0)]
        app = _make_app("testdb", "db:postgres")
        restore_database(mock_ssh, app, "/opt/infrakt/backups/testdb.sql.gz")

        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("gunzip" in c for c in calls)
        assert any("psql" in c for c in calls)

    def test_postgres_restore_custom_format_in_sql_gz_uses_pg_restore(self, mock_ssh):
        """Custom-format dump saved as .sql.gz should use pg_restore."""
        # docker inspect (resolve), test -f, gunzip magic check (PGDMP)
        mock_ssh.run.side_effect = [("", "", 0), ("", "", 0), ("PGDMP", "", 0)]
        app = _make_app("testdb", "db:postgres")
        restore_database(mock_ssh, app, "/opt/infrakt/backups/testdb.sql.gz")

        calls = [str(c) for c in mock_ssh.run_checked.call_args_list]
        assert any("pg_restore" in c for c in calls)
        assert any("gunzip" in c for c in calls)

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
