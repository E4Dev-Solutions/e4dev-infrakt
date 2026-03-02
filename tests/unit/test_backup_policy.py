"""Tests for the backup policy API endpoints and S3 cleanup safety rule."""

from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from api.main import app
from cli.core.backup import cleanup_old_s3_backups
from cli.core.database import init_db
from tests.conftest import TEST_API_KEY

client = TestClient(app)
HEADERS = {"X-API-Key": TEST_API_KEY}


# ── API endpoint tests ─────────────────────────────────────────────────────


class TestGetBackupPolicy:
    def test_returns_defaults_when_no_policy(self):
        init_db()
        r = client.get("/api/settings/backup-policy", headers=HEADERS)
        assert r.status_code == 200
        data = r.json()
        assert data["default_cron"] is None
        assert data["default_retention_days"] == 7
        assert data["s3_max_backups_per_db"] == 10
        assert data["s3_max_age_days"] == 30
        assert data["scheduled_count"] == 0
        assert data["total_count"] == 0


class TestSaveBackupPolicy:
    def test_save_and_get(self):
        init_db()
        body = {
            "default_cron": "0 3 * * *",
            "default_retention_days": 14,
            "s3_max_backups_per_db": 5,
            "s3_max_age_days": 60,
        }
        r = client.put("/api/settings/backup-policy", json=body, headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["message"] == "Backup policy saved"

        r2 = client.get("/api/settings/backup-policy", headers=HEADERS)
        data = r2.json()
        assert data["default_cron"] == "0 3 * * *"
        assert data["default_retention_days"] == 14
        assert data["s3_max_backups_per_db"] == 5
        assert data["s3_max_age_days"] == 60

    def test_rejects_invalid_cron(self):
        init_db()
        body = {"default_cron": "bad"}
        r = client.put("/api/settings/backup-policy", json=body, headers=HEADERS)
        assert r.status_code == 422

    def test_rejects_negative_retention(self):
        init_db()
        body = {"default_retention_days": 0}
        r = client.put("/api/settings/backup-policy", json=body, headers=HEADERS)
        assert r.status_code == 422


class TestApplyAll:
    def test_returns_400_when_no_policy(self):
        init_db()
        r = client.post("/api/settings/backup-policy/apply-all", headers=HEADERS)
        assert r.status_code == 400

    def test_returns_400_when_no_default_cron(self):
        init_db()
        # Save policy without cron
        client.put(
            "/api/settings/backup-policy",
            json={"default_cron": None},
            headers=HEADERS,
        )
        r = client.post("/api/settings/backup-policy/apply-all", headers=HEADERS)
        assert r.status_code == 400


class TestDisableAll:
    def test_returns_success_with_zero_when_nothing_scheduled(self):
        init_db()
        r = client.post("/api/settings/backup-policy/disable-all", headers=HEADERS)
        assert r.status_code == 200
        assert r.json()["count"] == 0


# ── S3 cleanup safety rule tests ────────────────────────────────────────────


class TestCleanupSafetyRule:
    """cleanup_old_s3_backups must never delete the latest backup."""

    def _make_backup(self, filename: str, modified: str) -> dict:
        return {
            "filename": filename,
            "size_bytes": 1000,
            "modified": modified,
        }

    @patch("cli.core.backup._cleanup_aws_credentials")
    @patch("cli.core.backup._write_aws_credentials")
    @patch("cli.core.backup.list_s3_backups")
    def test_single_backup_never_deleted(self, mock_list, mock_write, mock_cleanup):
        """Only one backup exists — it should never be deleted."""
        mock_list.return_value = [
            self._make_backup(
                "srv_db_postgres_abc12345_20250101_020000.sql.gz",
                "2025-01-01 02:00:00",
            )
        ]
        ssh = MagicMock()
        result = cleanup_old_s3_backups(
            ssh,
            s3_endpoint="https://s3.example.com",
            bucket="b",
            region="r",
            access_key="k",
            secret_key="s",
            prefix="infrakt/",
            db_type="postgres",
            backup_id="abc12345",
            keep=1,
            max_age_days=1,
        )
        assert result == 0
        ssh.run.assert_not_called()

    @patch("cli.core.backup._cleanup_aws_credentials")
    @patch("cli.core.backup._write_aws_credentials")
    @patch("cli.core.backup.list_s3_backups")
    def test_latest_preserved_when_keep_is_one(self, mock_list, mock_write, mock_cleanup):
        """With keep=1, only the oldest backup should be deleted."""
        mock_list.return_value = [
            self._make_backup(
                "srv_db_postgres_abc12345_20250102_020000.sql.gz",
                "2025-01-02 02:00:00",
            ),
            self._make_backup(
                "srv_db_postgres_abc12345_20250101_020000.sql.gz",
                "2025-01-01 02:00:00",
            ),
        ]
        ssh = MagicMock()
        ssh.run.return_value = ("", "", 0)
        result = cleanup_old_s3_backups(
            ssh,
            s3_endpoint="https://s3.example.com",
            bucket="b",
            region="r",
            access_key="k",
            secret_key="s",
            prefix="infrakt/",
            db_type="postgres",
            backup_id="abc12345",
            keep=1,
        )
        assert result == 1
        # The deleted file should be the older one
        call_str = str(ssh.run.call_args_list[0])
        assert "20250101" in call_str
        assert "20250102" not in call_str

    @patch("cli.core.backup._cleanup_aws_credentials")
    @patch("cli.core.backup._write_aws_credentials")
    @patch("cli.core.backup.list_s3_backups")
    def test_max_age_respects_latest_safety(self, mock_list, mock_write, mock_cleanup):
        """Even with max_age_days=1, the latest backup is preserved."""
        mock_list.return_value = [
            self._make_backup(
                "srv_db_postgres_abc12345_20200101_020000.sql.gz",
                "2020-01-01 02:00:00",  # very old
            ),
        ]
        ssh = MagicMock()
        result = cleanup_old_s3_backups(
            ssh,
            s3_endpoint="https://s3.example.com",
            bucket="b",
            region="r",
            access_key="k",
            secret_key="s",
            prefix="infrakt/",
            db_type="postgres",
            backup_id="abc12345",
            keep=10,
            max_age_days=1,
        )
        assert result == 0
        ssh.run.assert_not_called()

    @patch("cli.core.backup._cleanup_aws_credentials")
    @patch("cli.core.backup._write_aws_credentials")
    @patch("cli.core.backup.list_s3_backups")
    def test_max_age_deletes_old_candidates(self, mock_list, mock_write, mock_cleanup):
        """Old candidates are deleted but the latest is kept."""
        mock_list.return_value = [
            self._make_backup(
                "srv_db_postgres_abc12345_20260301_020000.sql.gz",
                "2026-03-01 02:00:00",  # recent
            ),
            self._make_backup(
                "srv_db_postgres_abc12345_20200601_020000.sql.gz",
                "2020-06-01 02:00:00",  # old
            ),
            self._make_backup(
                "srv_db_postgres_abc12345_20200101_020000.sql.gz",
                "2020-01-01 02:00:00",  # old
            ),
        ]
        ssh = MagicMock()
        ssh.run.return_value = ("", "", 0)
        result = cleanup_old_s3_backups(
            ssh,
            s3_endpoint="https://s3.example.com",
            bucket="b",
            region="r",
            access_key="k",
            secret_key="s",
            prefix="infrakt/",
            db_type="postgres",
            backup_id="abc12345",
            keep=10,
            max_age_days=30,
        )
        assert result == 2
