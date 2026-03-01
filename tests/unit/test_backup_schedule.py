"""Tests for scheduled backup functions in cli/core/backup.py.

Covers generate_backup_script, install_backup_cron, and remove_backup_cron.
"""

import types
from unittest.mock import MagicMock

import pytest

from cli.core.backup import (
    generate_backup_script,
    install_backup_cron,
    list_backups,
    remove_backup_cron,
)


def _make_app(name: str = "mydb", app_type: str = "db:postgres") -> types.SimpleNamespace:
    """Return a minimal app-like object with the attributes backup functions require."""
    return types.SimpleNamespace(name=name, app_type=app_type, parent_app_id=None)


# ---------------------------------------------------------------------------
# TestGenerateBackupScript
# ---------------------------------------------------------------------------


class TestGenerateBackupScript:
    def test_postgres_script_contains_pg_dump(self, isolated_config):
        """Postgres backup script includes pg_dump, the container name, and shell boilerplate."""
        app = _make_app(name="mydb", app_type="db:postgres")
        script = generate_backup_script(app)

        assert "#!/usr/bin/env bash" in script
        assert "set -euo pipefail" in script
        assert "pg_dump" in script
        assert "infrakt-db-mydb" in script

    def test_mysql_script_reads_password_from_env(self, isolated_config):
        """MySQL backup script reads the container password via printenv and calls mysqldump."""
        app = _make_app(name="mydb", app_type="db:mysql")
        script = generate_backup_script(app)

        assert "printenv MYSQL_PASSWORD" in script
        assert "mysqldump" in script

    def test_redis_script_uses_bgsave(self, isolated_config):
        """Redis backup script triggers BGSAVE and copies the dump file with docker cp."""
        app = _make_app(name="mydb", app_type="db:redis")
        script = generate_backup_script(app)

        assert "redis-cli BGSAVE" in script
        assert "docker cp" in script

    def test_mongo_script_uses_mongodump(self, isolated_config):
        """MongoDB backup script calls mongodump and reads MONGO_INITDB_ROOT_PASSWORD."""
        app = _make_app(name="mydb", app_type="db:mongo")
        script = generate_backup_script(app)

        assert "mongodump" in script
        assert "MONGO_INITDB_ROOT_PASSWORD" in script

    def test_retention_uses_find_delete(self, isolated_config):
        """Default retention policy emits a find … -mtime +7 -delete line."""
        app = _make_app(name="mydb", app_type="db:postgres")
        script = generate_backup_script(app)

        assert "find" in script
        assert "-mtime +7" in script
        assert "-delete" in script

    def test_custom_retention_days(self, isolated_config):
        """Passing retention_days=30 produces a -mtime +30 argument instead of the default."""
        app = _make_app(name="mydb", app_type="db:postgres")
        script = generate_backup_script(app, retention_days=30)

        assert "-mtime +30" in script
        assert "-mtime +7" not in script

    def test_unsupported_type_raises(self, isolated_config):
        """An unrecognised database type raises ValueError."""
        app = _make_app(name="mydb", app_type="db:cockroach")
        with pytest.raises(ValueError):
            generate_backup_script(app)


# ---------------------------------------------------------------------------
# TestInstallBackupCron
# ---------------------------------------------------------------------------


class TestInstallBackupCron:
    def _make_ssh(self) -> MagicMock:
        ssh = MagicMock()
        ssh.run_checked.return_value = ""
        ssh.upload_string.return_value = None
        return ssh

    def test_uploads_script_and_installs_cron(self, isolated_config):
        """install_backup_cron uploads the script, chmods it, then installs the cron entry."""
        app = _make_app(name="mydb", app_type="db:postgres")
        ssh = self._make_ssh()

        install_backup_cron(ssh, app, "0 2 * * *")

        # Script must have been uploaded
        ssh.upload_string.assert_called_once()
        upload_args = ssh.upload_string.call_args
        # First positional arg is the script content; second is the remote path
        script_content = upload_args[0][0]
        assert "pg_dump" in script_content

        # chmod +x must have been called
        chmod_calls = [str(c) for c in ssh.run_checked.call_args_list]
        assert any("chmod +x" in c for c in chmod_calls)

        # crontab installation must have been called
        assert any("crontab" in c for c in chmod_calls)

    def test_cron_line_contains_marker(self, isolated_config):
        """The crontab command sent to the server embeds the infrakt-backup marker."""
        app = _make_app(name="mydb", app_type="db:postgres")
        ssh = self._make_ssh()

        install_backup_cron(ssh, app, "0 2 * * *")

        crontab_calls = [str(c) for c in ssh.run_checked.call_args_list if "crontab" in str(c)]
        assert crontab_calls, "Expected at least one run_checked call containing 'crontab'"
        assert any("infrakt-backup:mydb" in c for c in crontab_calls)

    def test_cron_line_contains_expression(self, isolated_config):
        """The crontab command sent to the server embeds the requested cron expression."""
        app = _make_app(name="mydb", app_type="db:postgres")
        ssh = self._make_ssh()

        install_backup_cron(ssh, app, "0 2 * * *")

        crontab_calls = [str(c) for c in ssh.run_checked.call_args_list if "crontab" in str(c)]
        assert any("0 2 * * *" in c for c in crontab_calls)


# ---------------------------------------------------------------------------
# TestRemoveBackupCron
# ---------------------------------------------------------------------------


class TestRemoveBackupCron:
    def _make_ssh(self) -> MagicMock:
        ssh = MagicMock()
        ssh.run.return_value = ("", "", 0)
        return ssh

    def test_removes_cron_entry(self, isolated_config):
        """remove_backup_cron calls ssh.run with a grep -v command to strip the marker."""
        app = _make_app(name="mydb", app_type="db:postgres")
        ssh = self._make_ssh()

        remove_backup_cron(ssh, app)

        run_calls = [str(c) for c in ssh.run.call_args_list]
        assert any("grep -v" in c and "infrakt-backup:mydb" in c for c in run_calls), (
            "Expected a 'grep -v infrakt-backup:mydb' call to remove the cron entry"
        )

    def test_removes_script_file(self, isolated_config):
        """remove_backup_cron calls ssh.run with rm -f pointing at the backup script path."""
        app = _make_app(name="mydb", app_type="db:postgres")
        ssh = self._make_ssh()

        remove_backup_cron(ssh, app)

        run_calls = [str(c) for c in ssh.run.call_args_list]
        assert any("rm -f" in c and "backup-mydb.sh" in c for c in run_calls), (
            "Expected an 'rm -f … backup-mydb.sh' call to delete the script"
        )


# ---------------------------------------------------------------------------
# TestListBackups
# ---------------------------------------------------------------------------


class TestListBackups:
    def test_parses_find_output(self, isolated_config):
        """list_backups correctly parses find -printf output into structured dicts."""
        app = _make_app(name="mydb", app_type="db:postgres")
        ssh = MagicMock()
        ssh.run.return_value = (
            "mydb_20260224_120000.sql.gz\t1048576\t1740412800.0\n"
            "mydb_20260223_120000.sql.gz\t524288\t1740326400.0\n",
            "",
            0,
        )
        result = list_backups(ssh, app)
        assert len(result) == 2
        assert result[0]["filename"] == "mydb_20260224_120000.sql.gz"
        assert result[0]["size"] == "1.0 MB"
        assert result[0]["size_bytes"] == 1048576
        assert result[1]["size"] == "512.0 KB"

    def test_returns_empty_on_failure(self, isolated_config):
        """Returns empty list when find command fails (e.g. directory missing)."""
        app = _make_app(name="mydb", app_type="db:postgres")
        ssh = MagicMock()
        ssh.run.return_value = ("", "", 1)
        result = list_backups(ssh, app)
        assert result == []

    def test_returns_empty_on_no_output(self, isolated_config):
        """Returns empty list when find succeeds but finds no matching files."""
        app = _make_app(name="mydb", app_type="db:postgres")
        ssh = MagicMock()
        ssh.run.return_value = ("", "", 0)
        result = list_backups(ssh, app)
        assert result == []


# ---------------------------------------------------------------------------
# TestGenerateBackupScriptWithS3
# ---------------------------------------------------------------------------


class TestGenerateBackupScriptWithS3:
    def test_includes_aws_s3_cp_when_s3_config_provided(self, isolated_config):
        app = _make_app("testdb", "db:postgres")
        script = generate_backup_script(
            app,
            s3_endpoint="https://s3.amazonaws.com",
            s3_bucket="my-backups",
            s3_region="us-east-1",
            s3_access_key="AKID",
            s3_secret_key="SECRET",
            s3_prefix="infrakt/",
        )
        assert "aws s3 cp" in script
        assert "my-backups" in script

    def test_no_s3_when_config_not_provided(self, isolated_config):
        app = _make_app("testdb", "db:postgres")
        script = generate_backup_script(app)
        assert "aws s3 cp" not in script

    def test_s3_credentials_are_exported_and_unset(self, isolated_config):
        app = _make_app("testdb", "db:postgres")
        script = generate_backup_script(
            app,
            s3_endpoint="https://s3.amazonaws.com",
            s3_bucket="b",
            s3_region="r",
            s3_access_key="AK",
            s3_secret_key="SK",
            s3_prefix="",
        )
        assert "export AWS_ACCESS_KEY_ID=" in script
        assert "export AWS_SECRET_ACCESS_KEY=" in script
        assert "unset AWS_ACCESS_KEY_ID" in script
