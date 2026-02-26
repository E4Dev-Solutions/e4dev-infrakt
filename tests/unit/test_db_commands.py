"""Tests for the 'db backup', 'db restore', 'db schedule-backup', and
'db unschedule-backup' CLI commands in cli/commands/db.py."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from cli.commands.db import db
from cli.core.database import get_session, init_db
from cli.models.app import App
from cli.models.server import Server


@pytest.fixture
def runner():
    return CliRunner()


def _seed_server(name: str = "srv-1", host: str = "1.2.3.4") -> str:
    """Insert a server record into the isolated DB and return its name."""
    init_db()
    with get_session() as session:
        srv = Server(name=name, host=host, user="root", port=22, status="active")
        session.add(srv)
    return name


def _seed_db(name: str = "mydb", server_name: str = "srv-1", db_type: str = "postgres") -> str:
    """Insert a server + database app record and return the database name."""
    _seed_server(server_name)
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        db_app = App(
            name=name,
            server_id=srv.id,
            port=5432,
            app_type=f"db:{db_type}",
            status="running",
        )
        session.add(db_app)
    return name


# ---------------------------------------------------------------------------
# db backup
# ---------------------------------------------------------------------------


class TestBackupCommand:
    def test_backup_calls_backup_database(self, runner, isolated_config):
        """Happy path: backup_database is called and output confirms success."""
        _seed_db("mydb", "srv-1")
        with (
            patch("cli.commands.db.SSHClient") as mock_cls,
            patch("cli.commands.db.backup_database") as mock_backup,
            patch("cli.commands.db.status_spinner"),
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            mock_backup.return_value = "/opt/infrakt/backups/mydb_20260224_120000.sql.gz"

            result = runner.invoke(db, ["backup", "mydb", "--server", "srv-1"])

        assert result.exit_code == 0
        assert "backed up" in result.output
        mock_backup.assert_called_once()

    def test_backup_exits_1_for_unknown_server(self, runner, isolated_config):
        """When the server name does not exist in the DB, the command raises ServerNotFoundError."""
        result = runner.invoke(db, ["backup", "mydb", "--server", "ghost-server"])

        assert result.exit_code != 0

    def test_backup_exits_1_for_unknown_database(self, runner, isolated_config):
        """When the server exists but the named database is absent, exit code is 1."""
        _seed_server("srv-1")

        with (
            patch("cli.commands.db.SSHClient"),
            patch("cli.commands.db.status_spinner"),
        ):
            result = runner.invoke(db, ["backup", "nonexistent-db", "--server", "srv-1"])

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_backup_custom_output_path(self, runner, isolated_config):
        """When --output is given, ssh.download receives that custom local path."""
        _seed_db("mydb", "srv-1")
        with (
            patch("cli.commands.db.SSHClient") as mock_cls,
            patch("cli.commands.db.backup_database") as mock_backup,
            patch("cli.commands.db.status_spinner"),
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            remote_path = "/opt/infrakt/backups/mydb_20260224_120000.sql.gz"
            mock_backup.return_value = remote_path

            result = runner.invoke(
                db, ["backup", "mydb", "--server", "srv-1", "--output", "/tmp/custom.sql.gz"]
            )

        assert result.exit_code == 0
        mock_ssh.download.assert_called_once_with(remote_path, "/tmp/custom.sql.gz")

    def test_backup_creates_backups_dir(self, runner, isolated_config):
        """The backups directory is created (or already exists) and download is called."""
        _seed_db("mydb", "srv-1")
        with (
            patch("cli.commands.db.SSHClient") as mock_cls,
            patch("cli.commands.db.backup_database") as mock_backup,
            patch("cli.commands.db.status_spinner"),
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            mock_backup.return_value = "/opt/infrakt/backups/mydb_20260224_120000.sql.gz"

            result = runner.invoke(db, ["backup", "mydb", "--server", "srv-1"])

        assert result.exit_code == 0
        # download must have been called, meaning the backups dir was prepared first
        mock_ssh.download.assert_called_once()

    def test_backup_default_local_path_uses_backups_dir(self, runner, isolated_config):
        """Without --output the local file path defaults into BACKUPS_DIR."""
        backups_dir = isolated_config / "backups"

        _seed_db("mydb", "srv-1")
        with (
            patch("cli.commands.db.SSHClient") as mock_cls,
            patch("cli.commands.db.backup_database") as mock_backup,
            patch("cli.commands.db.status_spinner"),
            patch("cli.commands.db.BACKUPS_DIR", backups_dir),
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            filename = "mydb_20260224_120000.sql.gz"
            mock_backup.return_value = f"/opt/infrakt/backups/{filename}"

            result = runner.invoke(db, ["backup", "mydb", "--server", "srv-1"])

        assert result.exit_code == 0
        expected_local = str(backups_dir / filename)
        mock_ssh.download.assert_called_once_with(
            f"/opt/infrakt/backups/{filename}", expected_local
        )


# ---------------------------------------------------------------------------
# db restore
# ---------------------------------------------------------------------------


class TestRestoreCommand:
    def test_restore_calls_restore_database(self, runner, isolated_config, tmp_path):
        """Happy path: restore_database is called and output confirms success."""
        _seed_db("mydb", "srv-1")
        backup_file = tmp_path / "mydb_20260224_120000.sql.gz"
        backup_file.write_bytes(b"fake backup data")

        with (
            patch("cli.commands.db.SSHClient") as mock_cls,
            patch("cli.commands.db.restore_database") as mock_restore,
            patch("cli.commands.db.status_spinner"),
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh

            result = runner.invoke(db, ["restore", "mydb", str(backup_file), "--server", "srv-1"])

        assert result.exit_code == 0
        assert "restored" in result.output
        mock_restore.assert_called_once()

    def test_restore_exits_1_for_unknown_server(self, runner, isolated_config, tmp_path):
        """When the server name does not exist in the DB, the command raises ServerNotFoundError."""
        backup_file = tmp_path / "mydb.sql.gz"
        backup_file.write_bytes(b"fake backup data")

        result = runner.invoke(
            db, ["restore", "mydb", str(backup_file), "--server", "ghost-server"]
        )

        assert result.exit_code != 0

    def test_restore_exits_1_for_unknown_database(self, runner, isolated_config, tmp_path):
        """When the server exists but the named database is absent, exit code is 1."""
        _seed_server("srv-1")
        backup_file = tmp_path / "ghost.sql.gz"
        backup_file.write_bytes(b"fake backup data")

        with (
            patch("cli.commands.db.SSHClient"),
            patch("cli.commands.db.status_spinner"),
        ):
            result = runner.invoke(
                db, ["restore", "nonexistent-db", str(backup_file), "--server", "srv-1"]
            )

        assert result.exit_code == 1
        assert "not found" in result.output

    def test_restore_uploads_file_to_remote(self, runner, isolated_config, tmp_path):
        """ssh.upload receives the local file path and a remote path under /opt/infrakt/backups/."""
        _seed_db("mydb", "srv-1")
        backup_file = tmp_path / "mydb_20260224_120000.sql.gz"
        backup_file.write_bytes(b"fake backup data")

        with (
            patch("cli.commands.db.SSHClient") as mock_cls,
            patch("cli.commands.db.restore_database"),
            patch("cli.commands.db.status_spinner"),
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh

            result = runner.invoke(db, ["restore", "mydb", str(backup_file), "--server", "srv-1"])

        assert result.exit_code == 0
        expected_remote = "/opt/infrakt/backups/mydb_20260224_120000.sql.gz"
        mock_ssh.upload.assert_called_once_with(str(backup_file), expected_remote)

    def test_restore_creates_remote_backup_dir(self, runner, isolated_config, tmp_path):
        """ssh.run_checked is called with 'mkdir -p /opt/infrakt/backups' before upload."""
        _seed_db("mydb", "srv-1")
        backup_file = tmp_path / "mydb_20260224_120000.sql.gz"
        backup_file.write_bytes(b"fake backup data")

        with (
            patch("cli.commands.db.SSHClient") as mock_cls,
            patch("cli.commands.db.restore_database"),
            patch("cli.commands.db.status_spinner"),
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh

            result = runner.invoke(db, ["restore", "mydb", str(backup_file), "--server", "srv-1"])

        assert result.exit_code == 0
        mock_ssh.run_checked.assert_any_call("mkdir -p /opt/infrakt/backups")


# ---------------------------------------------------------------------------
# db schedule-backup
# ---------------------------------------------------------------------------


class TestScheduleBackupCommand:
    def test_schedule_backup_installs_cron(self, runner, isolated_config):
        """Happy path: install_backup_cron is called and output confirms the schedule."""
        _seed_db("mydb", "srv-1")
        with (
            patch("cli.commands.db.SSHClient") as mock_cls,
            patch("cli.commands.db.install_backup_cron") as mock_install,
            patch("cli.commands.db.status_spinner"),
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh

            result = runner.invoke(
                db,
                ["schedule-backup", "mydb", "--server", "srv-1", "--cron", "0 2 * * *"],
            )

        assert result.exit_code == 0
        assert "Scheduled" in result.output
        mock_install.assert_called_once()

    def test_schedule_backup_exits_1_for_unknown_database(self, runner, isolated_config):
        """When the server exists but the named database is absent, exit code is 1."""
        _seed_server("srv-1")

        with (
            patch("cli.commands.db.SSHClient"),
            patch("cli.commands.db.status_spinner"),
        ):
            result = runner.invoke(
                db,
                [
                    "schedule-backup",
                    "nonexistent-db",
                    "--server",
                    "srv-1",
                    "--cron",
                    "0 2 * * *",
                ],
            )

        assert result.exit_code == 1
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# db unschedule-backup
# ---------------------------------------------------------------------------


class TestUnscheduleBackupCommand:
    def test_unschedule_backup_removes_cron(self, runner, isolated_config):
        """Happy path: remove_backup_cron is called and output confirms removal."""
        _seed_db("mydb", "srv-1")
        with (
            patch("cli.commands.db.SSHClient") as mock_cls,
            patch("cli.commands.db.remove_backup_cron") as mock_remove,
            patch("cli.commands.db.status_spinner"),
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh

            result = runner.invoke(db, ["unschedule-backup", "mydb", "--server", "srv-1"])

        assert result.exit_code == 0
        assert "Removed" in result.output
        mock_remove.assert_called_once()

    def test_unschedule_backup_exits_1_for_unknown_database(self, runner, isolated_config):
        """When the server exists but the named database is absent, exit code is 1."""
        _seed_server("srv-1")

        with (
            patch("cli.commands.db.SSHClient"),
            patch("cli.commands.db.status_spinner"),
        ):
            result = runner.invoke(db, ["unschedule-backup", "nonexistent-db", "--server", "srv-1"])

        assert result.exit_code == 1
        assert "not found" in result.output


# ---------------------------------------------------------------------------
# db backups
# ---------------------------------------------------------------------------


class TestBackupsCommand:
    def test_lists_backups(self, runner, isolated_config):
        """Happy path: list_backups_fn is called and output shows filenames."""
        _seed_db("mydb", "srv-1")
        with (
            patch("cli.commands.db.SSHClient") as mock_cls,
            patch("cli.commands.db.list_backups_fn") as mock_list,
            patch("cli.commands.db.status_spinner"),
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            mock_list.return_value = [
                {
                    "filename": "mydb_20260224_120000.sql.gz",
                    "size": "1.0 MB",
                    "size_bytes": 1048576,
                    "modified": "2026-02-24T12:00:00+00:00",
                }
            ]
            result = runner.invoke(db, ["backups", "mydb", "--server", "srv-1"])
        assert result.exit_code == 0
        assert "mydb_20260224_120000.sql.gz" in result.output

    def test_shows_no_backups_message(self, runner, isolated_config):
        """When no backups exist, shows 'No backups found' message."""
        _seed_db("mydb", "srv-1")
        with (
            patch("cli.commands.db.SSHClient") as mock_cls,
            patch("cli.commands.db.list_backups_fn") as mock_list,
            patch("cli.commands.db.status_spinner"),
        ):
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            mock_list.return_value = []
            result = runner.invoke(db, ["backups", "mydb", "--server", "srv-1"])
        assert result.exit_code == 0
        assert "No backups" in result.output

    def test_exits_1_for_unknown_database(self, runner, isolated_config):
        """When database not found, exits with code 1."""
        _seed_server("srv-1")
        with patch("cli.commands.db.status_spinner"):
            result = runner.invoke(db, ["backups", "ghost", "--server", "srv-1"])
        assert result.exit_code == 1


# ---------------------------------------------------------------------------
# db info
# ---------------------------------------------------------------------------


class TestInfoCommand:
    def test_shows_database_info(self, runner, isolated_config):
        """Happy path: info command prints database details."""
        _seed_db("mydb", "srv-1")
        with patch("cli.commands.db.SSHClient"):
            result = runner.invoke(db, ["info", "mydb", "--server", "srv-1"])
        assert result.exit_code == 0
        assert "mydb" in result.output
        assert "postgres" in result.output

    def test_exits_1_for_unknown_database(self, runner, isolated_config):
        """When database not found, exits with code 1."""
        _seed_server("srv-1")
        result = runner.invoke(db, ["info", "ghost", "--server", "srv-1"])
        assert result.exit_code == 1
