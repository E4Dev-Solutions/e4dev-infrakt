"""Tests for S3 backup upload/download functions."""

from unittest.mock import MagicMock

from cli.core.backup import download_backup_from_s3, list_s3_backups, upload_backup_to_s3


class TestUploadBackupToS3:
    def test_uploads_file_to_s3(self):
        ssh = MagicMock()
        ssh.run_checked.return_value = ""
        ssh.run.return_value = ("", "", 0)
        upload_backup_to_s3(
            ssh,
            local_path="/opt/infrakt/backups/mydb_20260228_020000.sql.gz",
            s3_endpoint="https://s3.amazonaws.com",
            bucket="my-backups",
            region="us-east-1",
            access_key="AKID",
            secret_key="SECRET",
            prefix="infrakt/",
            db_name="mydb",
        )
        calls = [str(c) for c in ssh.run_checked.call_args_list]
        assert any("aws s3 cp" in c for c in calls)
        assert any("my-backups" in c for c in calls)

    def test_cleans_up_credentials_file(self):
        ssh = MagicMock()
        ssh.run_checked.return_value = ""
        ssh.run.return_value = ("", "", 0)
        upload_backup_to_s3(
            ssh,
            local_path="/opt/infrakt/backups/test.sql.gz",
            s3_endpoint="https://s3.amazonaws.com",
            bucket="b",
            region="r",
            access_key="k",
            secret_key="s",
            prefix="",
            db_name="test",
        )
        calls = [str(c) for c in ssh.run.call_args_list]
        assert any("rm -f" in c for c in calls)


class TestDownloadBackupFromS3:
    def test_downloads_file_from_s3(self):
        ssh = MagicMock()
        ssh.run_checked.return_value = ""
        ssh.run.return_value = ("", "", 0)
        result = download_backup_from_s3(
            ssh,
            filename="mydb_20260228_020000.sql.gz",
            s3_endpoint="https://s3.amazonaws.com",
            bucket="my-backups",
            region="us-east-1",
            access_key="AKID",
            secret_key="SECRET",
            prefix="infrakt/",
            db_name="mydb",
        )
        assert result == "/opt/infrakt/backups/mydb_20260228_020000.sql.gz"
        calls = [str(c) for c in ssh.run_checked.call_args_list]
        assert any("aws s3 cp" in c for c in calls)


class TestListS3Backups:
    def test_parses_s3_ls_output(self):
        ssh = MagicMock()
        ssh.run_checked.return_value = ""
        ssh.run.return_value = (
            "2026-02-28 02:00:00    2516582 mydb_20260228_020000.sql.gz\n"
            "2026-02-27 02:00:00    2202009 mydb_20260227_020000.sql.gz\n",
            "",
            0,
        )
        results = list_s3_backups(
            ssh,
            s3_endpoint="https://s3.amazonaws.com",
            bucket="b",
            region="r",
            access_key="k",
            secret_key="s",
            prefix="infrakt/",
            db_name="mydb",
        )
        assert len(results) == 2
        assert results[0]["filename"] == "mydb_20260228_020000.sql.gz"
        assert results[0]["size_bytes"] == 2516582

    def test_returns_empty_for_no_files(self):
        ssh = MagicMock()
        ssh.run_checked.return_value = ""
        ssh.run.return_value = ("", "", 1)
        results = list_s3_backups(
            ssh,
            s3_endpoint="https://s3.amazonaws.com",
            bucket="b",
            region="r",
            access_key="k",
            secret_key="s",
            prefix="",
            db_name="mydb",
        )
        assert results == []
