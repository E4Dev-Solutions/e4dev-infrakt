"""Tests for server metrics features in api/routes/servers.py.

Covers the _parse_cpu helper, the GET /api/servers/{name}/metrics endpoint,
and the side-effect of GET /api/servers/{name}/status that records a
ServerMetric snapshot.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes.servers import _parse_cpu
from cli.core.database import get_session, init_db
from cli.models.server import Server
from cli.models.server_metric import ServerMetric
from tests.conftest import TEST_API_KEY


@pytest.fixture
def client(isolated_config):
    """Return a TestClient backed by the isolated (temp) database."""
    return TestClient(app, headers={"X-API-Key": TEST_API_KEY})


def _seed_server(
    name: str = "test-srv",
    host: str = "1.2.3.4",
    user: str = "root",
    status: str = "active",
) -> int:
    """Insert a Server into the isolated DB; returns the server's primary key."""
    init_db()
    with get_session() as session:
        srv = Server(name=name, host=host, user=user, port=22, status=status)
        session.add(srv)
        session.flush()
        return srv.id


# ---------------------------------------------------------------------------
# _parse_cpu unit tests
# ---------------------------------------------------------------------------


class TestParseCpu:
    def test_parse_cpu_valid(self):
        """_parse_cpu returns a float for a well-formed decimal string."""
        result = _parse_cpu("12.3")
        assert result == 12.3

    def test_parse_cpu_rounds_to_one_decimal(self):
        """_parse_cpu rounds to one decimal place."""
        result = _parse_cpu("45.678")
        assert result == 45.7

    def test_parse_cpu_integer_string(self):
        """_parse_cpu accepts an integer-formatted string."""
        result = _parse_cpu("50")
        assert result == 50.0

    def test_parse_cpu_strips_surrounding_whitespace(self):
        """_parse_cpu handles leading/trailing whitespace."""
        result = _parse_cpu("  8.5  ")
        assert result == 8.5

    def test_parse_cpu_invalid(self):
        """_parse_cpu returns None for non-numeric input."""
        result = _parse_cpu("bad")
        assert result is None

    def test_parse_cpu_empty(self):
        """_parse_cpu returns None for an empty string."""
        result = _parse_cpu("")
        assert result is None

    def test_parse_cpu_none_input(self):
        """_parse_cpu returns None when passed None (AttributeError path)."""
        result = _parse_cpu(None)
        assert result is None

    def test_parse_cpu_zero(self):
        """_parse_cpu correctly handles zero."""
        result = _parse_cpu("0.0")
        assert result == 0.0

    def test_parse_cpu_100_percent(self):
        """_parse_cpu handles 100% CPU."""
        result = _parse_cpu("100.0")
        assert result == 100.0


# ---------------------------------------------------------------------------
# GET /api/servers/{name}/metrics
# ---------------------------------------------------------------------------


class TestMetricsEndpoint:
    def test_metrics_endpoint_empty(self, client, isolated_config):
        """GET /api/servers/{name}/metrics returns [] when no metrics exist."""
        _seed_server("metrics-empty")
        response = client.get("/api/servers/metrics-empty/metrics")
        assert response.status_code == 200
        assert response.json() == []

    def test_metrics_endpoint_returns_data(self, client, isolated_config):
        """GET /api/servers/{name}/metrics returns seeded metric rows."""
        srv_id = _seed_server("metrics-data")
        now = datetime.now(UTC)
        init_db()
        with get_session() as session:
            session.add(
                ServerMetric(
                    server_id=srv_id,
                    recorded_at=now,
                    cpu_percent=15.5,
                    mem_percent=42.0,
                    disk_percent=30.1,
                )
            )

        response = client.get("/api/servers/metrics-data/metrics")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["cpu_percent"] == 15.5
        assert data[0]["mem_percent"] == 42.0
        assert data[0]["disk_percent"] == 30.1

    def test_metrics_endpoint_response_schema(self, client, isolated_config):
        """Each metric record contains the expected schema fields."""
        srv_id = _seed_server("metrics-schema")
        with get_session() as session:
            session.add(
                ServerMetric(
                    server_id=srv_id,
                    recorded_at=datetime.now(UTC),
                    cpu_percent=10.0,
                    mem_percent=20.0,
                    disk_percent=30.0,
                )
            )

        data = client.get("/api/servers/metrics-schema/metrics").json()
        record = data[0]
        expected = ("id", "server_id", "recorded_at", "cpu_percent", "mem_percent", "disk_percent")
        for field in expected:
            assert field in record, f"Missing field: {field}"

    def test_metrics_endpoint_filters_by_hours(self, client, isolated_config):
        """hours=1 must exclude metric rows older than one hour."""
        srv_id = _seed_server("metrics-filter")
        now = datetime.now(UTC)
        old_time = now - timedelta(hours=3)
        recent_time = now - timedelta(minutes=10)

        with get_session() as session:
            session.add(
                ServerMetric(
                    server_id=srv_id,
                    recorded_at=old_time,
                    cpu_percent=99.0,
                    mem_percent=99.0,
                    disk_percent=99.0,
                )
            )
            session.add(
                ServerMetric(
                    server_id=srv_id,
                    recorded_at=recent_time,
                    cpu_percent=5.0,
                    mem_percent=5.0,
                    disk_percent=5.0,
                )
            )

        response = client.get("/api/servers/metrics-filter/metrics?hours=1")
        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["cpu_percent"] == 5.0

    def test_metrics_endpoint_default_includes_24h_window(self, client, isolated_config):
        """Without hours param, metrics from the past 24 hours are returned."""
        srv_id = _seed_server("metrics-24h")
        now = datetime.now(UTC)

        with get_session() as session:
            # 12 hours ago — should be within the default 24h window
            session.add(
                ServerMetric(
                    server_id=srv_id,
                    recorded_at=now - timedelta(hours=12),
                    cpu_percent=50.0,
                    mem_percent=50.0,
                    disk_percent=50.0,
                )
            )
            # 25 hours ago — should be excluded
            session.add(
                ServerMetric(
                    server_id=srv_id,
                    recorded_at=now - timedelta(hours=25),
                    cpu_percent=99.0,
                    mem_percent=99.0,
                    disk_percent=99.0,
                )
            )

        data = client.get("/api/servers/metrics-24h/metrics").json()
        assert len(data) == 1
        assert data[0]["cpu_percent"] == 50.0

    def test_metrics_endpoint_returns_records_in_ascending_order(self, client, isolated_config):
        """Metric records are returned chronologically (oldest first)."""
        srv_id = _seed_server("metrics-order")
        now = datetime.now(UTC)

        with get_session() as session:
            session.add(
                ServerMetric(
                    server_id=srv_id,
                    recorded_at=now - timedelta(hours=2),
                    cpu_percent=1.0,
                    mem_percent=1.0,
                    disk_percent=1.0,
                )
            )
            session.add(
                ServerMetric(
                    server_id=srv_id,
                    recorded_at=now - timedelta(hours=1),
                    cpu_percent=2.0,
                    mem_percent=2.0,
                    disk_percent=2.0,
                )
            )

        data = client.get("/api/servers/metrics-order/metrics").json()
        assert data[0]["cpu_percent"] == 1.0
        assert data[1]["cpu_percent"] == 2.0

    def test_metrics_endpoint_server_not_found(self, client, isolated_config):
        """GET /api/servers/nonexistent/metrics returns 404."""
        init_db()
        response = client.get("/api/servers/nonexistent/metrics")
        assert response.status_code == 404
        assert "nonexistent" in response.json()["detail"]

    def test_metrics_endpoint_isolates_by_server(self, client, isolated_config):
        """Metrics for server A must not appear in server B's response."""
        id_a = _seed_server("srv-a", host="1.1.1.1")
        _seed_server("srv-b", host="2.2.2.2")
        now = datetime.now(UTC)

        with get_session() as session:
            session.add(
                ServerMetric(
                    server_id=id_a,
                    recorded_at=now,
                    cpu_percent=77.0,
                    mem_percent=77.0,
                    disk_percent=77.0,
                )
            )

        data = client.get("/api/servers/srv-b/metrics").json()
        assert data == []


# ---------------------------------------------------------------------------
# GET /api/servers/{name}/status — ServerMetric persistence side-effect
# ---------------------------------------------------------------------------


class TestStatusRecordsMetric:
    def _make_mock_ssh(self, cpu_raw: str = "25.0") -> MagicMock:
        """Build a MagicMock SSHClient that returns plausible system output."""
        mock_ssh = MagicMock()
        mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
        mock_ssh.__exit__ = MagicMock(return_value=False)
        mock_ssh.run_checked.return_value = "up 5 days"
        mock_ssh.run.side_effect = [
            # free -b output: total used free
            ("8000000000 2000000000 5000000000", "", 0),
            # df -B1 / output: total used avail percent
            ("20000000000 5000000000 14000000000 25%", "", 0),
            # top CPU output
            (cpu_raw, "", 0),
            # docker ps output
            ("", "", 0),
        ]
        return mock_ssh

    @patch("api.routes.servers.SSHClient")
    def test_status_records_metric(self, mock_ssh_cls, client, isolated_config):
        """Calling GET /api/servers/{name}/status persists a ServerMetric row."""
        srv_id = _seed_server("test-srv")

        mock_ssh = self._make_mock_ssh("25.0")
        mock_ssh_cls.from_server.return_value = mock_ssh

        response = client.get("/api/servers/test-srv/status")
        assert response.status_code == 200

        # Read all attribute values inside the open session to avoid DetachedInstanceError
        with get_session() as session:
            metrics = session.query(ServerMetric).filter(ServerMetric.server_id == srv_id).all()
            cpu_values = [m.cpu_percent for m in metrics]

        assert len(cpu_values) == 1
        assert cpu_values[0] == 25.0

    @patch("api.routes.servers.SSHClient")
    def test_status_records_memory_and_disk_percent(self, mock_ssh_cls, client, isolated_config):
        """The persisted ServerMetric captures mem_percent and disk_percent as well."""
        srv_id = _seed_server("mem-disk-srv")

        mock_ssh = self._make_mock_ssh("10.0")
        mock_ssh_cls.from_server.return_value = mock_ssh

        client.get("/api/servers/mem-disk-srv/status")

        # Read all attribute values inside the open session to avoid DetachedInstanceError
        with get_session() as session:
            metric = session.query(ServerMetric).filter(ServerMetric.server_id == srv_id).first()
            mem_pct = metric.mem_percent if metric else None
            disk_pct = metric.disk_percent if metric else None

        assert mem_pct is not None
        assert disk_pct is not None
        # free -b: 2000000000 / 8000000000 = 25 %
        assert mem_pct == 25.0
        # df: 25%
        assert disk_pct == 25.0

    @patch("api.routes.servers.SSHClient")
    def test_status_records_none_cpu_when_unparseable(self, mock_ssh_cls, client, isolated_config):
        """cpu_percent is stored as None when the top output cannot be parsed."""
        srv_id = _seed_server("cpu-none-srv")

        mock_ssh = MagicMock()
        mock_ssh.__enter__ = MagicMock(return_value=mock_ssh)
        mock_ssh.__exit__ = MagicMock(return_value=False)
        mock_ssh.run_checked.return_value = "up 1 day"
        mock_ssh.run.side_effect = [
            ("8000000000 2000000000 5000000000", "", 0),
            ("20000000000 5000000000 14000000000 25%", "", 0),
            # Unparseable CPU string
            ("n/a", "", 0),
            ("", "", 0),
        ]
        mock_ssh_cls.from_server.return_value = mock_ssh

        client.get("/api/servers/cpu-none-srv/status")

        # Read all attribute values inside the open session to avoid DetachedInstanceError
        with get_session() as session:
            metric = session.query(ServerMetric).filter(ServerMetric.server_id == srv_id).first()
            cpu_pct = metric.cpu_percent if metric else "MISSING"
            found = metric is not None

        assert found
        assert cpu_pct is None

    @patch("api.routes.servers.SSHClient")
    def test_status_each_call_appends_a_new_metric(self, mock_ssh_cls, client, isolated_config):
        """Each call to the status endpoint adds a new row — it does not overwrite."""
        srv_id = _seed_server("multi-call-srv")

        for _ in range(3):
            mock_ssh = self._make_mock_ssh("30.0")
            mock_ssh_cls.from_server.return_value = mock_ssh
            client.get("/api/servers/multi-call-srv/status")

        with get_session() as session:
            count = session.query(ServerMetric).filter(ServerMetric.server_id == srv_id).count()

        assert count == 3
