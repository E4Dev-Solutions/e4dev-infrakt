"""Tests for FastAPI /api/databases routes.

Covers backup, restore, schedule, and unschedule endpoints.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from cli.core.database import get_session, init_db
from cli.models.app import App
from cli.models.server import Server
from tests.conftest import TEST_API_KEY


@pytest.fixture
def client(isolated_config):
    """Return a TestClient backed by the isolated (temp) database."""
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})


def _seed_db(name="testdb", server_name="srv-1", db_type="postgres"):
    """Seed a server + database app for testing."""
    init_db()
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            srv = Server(name=server_name, host="1.2.3.4", user="root", port=22, status="active")
            session.add(srv)
            session.flush()
        db_app = App(
            name=name,
            server_id=srv.id,
            port=5432,
            app_type=f"db:{db_type}",
            status="running",
        )
        session.add(db_app)


class TestBackupEndpoint:
    def test_returns_filename_on_success(self, client, isolated_config):
        _seed_db("mydb")
        with patch("api.routes.databases.SSHClient") as mock_cls:
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh

            with patch("api.routes.databases.backup_database") as mock_backup:
                mock_backup.return_value = "/opt/infrakt/backups/mydb_20260224_120000.sql.gz"
                response = client.post("/api/databases/mydb/backup")

        assert response.status_code == 200
        data = response.json()
        assert data["filename"] == "mydb_20260224_120000.sql.gz"
        assert "Backup created" in data["message"]

    def test_returns_404_for_unknown_database(self, client, isolated_config):
        response = client.post("/api/databases/ghost/backup")
        assert response.status_code == 404

    def test_filters_by_server_name(self, client, isolated_config):
        _seed_db("mydb", server_name="srv-1")
        response = client.post("/api/databases/mydb/backup?server=wrong-server")
        assert response.status_code == 404


class TestRestoreEndpoint:
    def test_returns_success_message(self, client, isolated_config):
        _seed_db("mydb")
        with patch("api.routes.databases.SSHClient") as mock_cls:
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh

            with patch("api.routes.databases.restore_database"):
                response = client.post(
                    "/api/databases/mydb/restore",
                    json={"filename": "mydb_20260224_120000.sql.gz"},
                )

        assert response.status_code == 200
        assert "restored" in response.json()["message"]

    def test_returns_404_for_unknown_database(self, client, isolated_config):
        response = client.post(
            "/api/databases/ghost/restore",
            json={"filename": "ghost.sql.gz"},
        )
        assert response.status_code == 404

    def test_returns_404_for_missing_backup_file(self, client, isolated_config):
        from cli.core.exceptions import SSHConnectionError

        _seed_db("mydb")
        with patch("api.routes.databases.SSHClient") as mock_cls:
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh

            with patch(
                "api.routes.databases.restore_database",
                side_effect=SSHConnectionError("Backup file not found on server: missing.sql.gz"),
            ):
                response = client.post(
                    "/api/databases/mydb/restore",
                    json={"filename": "missing.sql.gz"},
                )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"]


# ---------------------------------------------------------------------------
# POST /api/databases/{name}/schedule
# ---------------------------------------------------------------------------


class TestScheduleEndpoint:
    def test_schedule_returns_success(self, client, isolated_config):
        """Happy path: install_backup_cron is invoked and the response confirms scheduling."""
        _seed_db("mydb")
        with patch("api.routes.databases.SSHClient") as mock_cls:
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh

            with patch("api.routes.databases.install_backup_cron") as mock_install:
                response = client.post(
                    "/api/databases/mydb/schedule",
                    json={"cron_expression": "0 2 * * *", "retention_days": 7},
                )

        assert response.status_code == 200
        assert "Scheduled" in response.json()["message"]
        mock_install.assert_called_once()

    def test_schedule_returns_404_for_unknown_db(self, client, isolated_config):
        """Scheduling a non-existent database returns 404."""
        response = client.post(
            "/api/databases/ghost/schedule",
            json={"cron_expression": "0 2 * * *", "retention_days": 7},
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/databases/{name}/schedule
# ---------------------------------------------------------------------------


class TestUnscheduleEndpoint:
    def test_unschedule_returns_success(self, client, isolated_config):
        """Happy path: remove_backup_cron is invoked and the response confirms removal."""
        _seed_db("mydb")
        with patch("api.routes.databases.SSHClient") as mock_cls:
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh

            with patch("api.routes.databases.remove_backup_cron") as mock_remove:
                response = client.delete("/api/databases/mydb/schedule")

        assert response.status_code == 200
        assert "Removed" in response.json()["message"]
        mock_remove.assert_called_once()

    def test_unschedule_returns_404_for_unknown_db(self, client, isolated_config):
        """Unscheduling a non-existent database returns 404."""
        response = client.delete("/api/databases/ghost/schedule")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/databases/{name}
# ---------------------------------------------------------------------------


class TestGetDatabaseEndpoint:
    def test_returns_database_details(self, client, isolated_config):
        """GET /databases/{name} returns database details with new fields."""
        _seed_db("mydb")
        response = client.get("/api/databases/mydb")
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "mydb"
        assert data["db_type"] == "postgres"
        assert "backup_schedule" in data
        assert "created_at" in data

    def test_returns_404_for_unknown(self, client, isolated_config):
        """GET /databases/{name} returns 404 for non-existent database."""
        response = client.get("/api/databases/ghost")
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/databases/{name}/backups
# ---------------------------------------------------------------------------


class TestListBackupsEndpoint:
    def test_returns_backup_list(self, client, isolated_config):
        """GET /databases/{name}/backups returns backup file list."""
        _seed_db("mydb")
        with patch("api.routes.databases.SSHClient") as mock_cls:
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            with patch("api.routes.databases.list_backups") as mock_list:
                mock_list.return_value = [
                    {
                        "filename": "mydb_20260224.sql.gz",
                        "size": "1.0 MB",
                        "size_bytes": 1048576,
                        "modified": "2026-02-24T12:00:00+00:00",
                    }
                ]
                response = client.get("/api/databases/mydb/backups")
        assert response.status_code == 200
        assert len(response.json()) == 1
        assert response.json()[0]["filename"] == "mydb_20260224.sql.gz"

    def test_returns_empty_on_ssh_failure(self, client, isolated_config):
        """GET /databases/{name}/backups returns empty list when server is unreachable."""
        from cli.core.exceptions import SSHConnectionError

        _seed_db("mydb")
        with patch("api.routes.databases.SSHClient") as mock_cls:
            mock_ssh = MagicMock()
            mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
            mock_ssh.__exit__ = MagicMock(return_value=False)
            mock_cls.from_server.return_value = mock_ssh
            with patch(
                "api.routes.databases.list_backups",
                side_effect=SSHConnectionError("offline"),
            ):
                response = client.get("/api/databases/mydb/backups")
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_404_for_unknown_database(self, client, isolated_config):
        """GET /databases/{name}/backups returns 404 for non-existent database."""
        response = client.get("/api/databases/ghost/backups")
        assert response.status_code == 404
