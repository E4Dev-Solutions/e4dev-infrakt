"""Tests for cli/core/health.py — check_app_health via SSH curl."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cli.core.health import check_app_health


def _make_ssh(stdout: str = "", stderr: str = "", exit_code: int = 0) -> MagicMock:
    """Return a mock SSHClient with a pre-configured run() return value."""
    ssh = MagicMock()
    ssh.run.return_value = (stdout, stderr, exit_code)
    return ssh


# ---------------------------------------------------------------------------
# Healthy responses
# ---------------------------------------------------------------------------


class TestHealthyResponse:
    def test_200_status_returns_healthy_true(self):
        ssh = _make_ssh(stdout="200 0.042")
        result = check_app_health(ssh, port=8080, health_path="/health")
        assert result["healthy"] is True

    def test_200_sets_correct_status_code(self):
        ssh = _make_ssh(stdout="200 0.042")
        result = check_app_health(ssh, port=8080, health_path="/health")
        assert result["status_code"] == 200

    def test_200_sets_response_time_in_ms(self):
        ssh = _make_ssh(stdout="200 0.042")
        result = check_app_health(ssh, port=8080, health_path="/health")
        assert result["response_time_ms"] == pytest.approx(42.0, abs=0.5)

    def test_301_redirect_is_healthy(self):
        ssh = _make_ssh(stdout="301 0.010")
        result = check_app_health(ssh, port=3000, health_path="/")
        assert result["healthy"] is True
        assert result["status_code"] == 301

    def test_399_boundary_is_healthy(self):
        ssh = _make_ssh(stdout="399 0.020")
        result = check_app_health(ssh, port=3000, health_path="/ping")
        assert result["healthy"] is True

    def test_error_is_none_on_success(self):
        ssh = _make_ssh(stdout="200 0.005")
        result = check_app_health(ssh, port=3000, health_path="/")
        assert result["error"] is None


# ---------------------------------------------------------------------------
# Unhealthy responses
# ---------------------------------------------------------------------------


class TestUnhealthyResponse:
    def test_400_returns_unhealthy(self):
        ssh = _make_ssh(stdout="400 0.010")
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["healthy"] is False
        assert result["status_code"] == 400

    def test_404_returns_unhealthy(self):
        ssh = _make_ssh(stdout="404 0.008")
        result = check_app_health(ssh, port=3000, health_path="/missing")
        assert result["healthy"] is False

    def test_500_returns_unhealthy(self):
        ssh = _make_ssh(stdout="500 0.003")
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["healthy"] is False
        assert result["status_code"] == 500

    def test_503_returns_unhealthy(self):
        ssh = _make_ssh(stdout="503 0.001")
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["healthy"] is False


# ---------------------------------------------------------------------------
# Connection / curl failures
# ---------------------------------------------------------------------------


class TestConnectionFailure:
    def test_nonzero_exit_code_returns_unhealthy(self):
        ssh = _make_ssh(stdout="", stderr="Connection refused", exit_code=7)
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["healthy"] is False

    def test_nonzero_exit_sets_status_code_to_none(self):
        ssh = _make_ssh(stdout="", stderr="timed out", exit_code=28)
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["status_code"] is None

    def test_nonzero_exit_sets_response_time_to_none(self):
        ssh = _make_ssh(stdout="", stderr="timed out", exit_code=28)
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["response_time_ms"] is None

    def test_nonzero_exit_captures_stderr_as_error(self):
        ssh = _make_ssh(stdout="", stderr="Connection refused", exit_code=7)
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["error"] == "Connection refused"

    def test_nonzero_exit_with_no_stderr_uses_exit_code_message(self):
        ssh = _make_ssh(stdout="", stderr="", exit_code=6)
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert "6" in result["error"]

    def test_timeout_curl_exit_code_28_is_unhealthy(self):
        # curl exit code 28 = operation timed out
        ssh = _make_ssh(stdout="", stderr="Operation timed out", exit_code=28)
        result = check_app_health(ssh, port=8080, health_path="/health")
        assert result["healthy"] is False


# ---------------------------------------------------------------------------
# Malformed curl output
# ---------------------------------------------------------------------------


class TestMalformedOutput:
    def test_empty_stdout_with_zero_exit_returns_unhealthy(self):
        ssh = _make_ssh(stdout="", exit_code=0)
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["healthy"] is False

    def test_non_numeric_status_code_returns_unhealthy(self):
        ssh = _make_ssh(stdout="not_a_code 0.01", exit_code=0)
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["healthy"] is False
        assert "Unexpected curl output" in result["error"]

    def test_only_one_field_in_stdout_returns_unhealthy(self):
        ssh = _make_ssh(stdout="200", exit_code=0)
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["healthy"] is False


# ---------------------------------------------------------------------------
# URL construction
# ---------------------------------------------------------------------------


class TestUrlConstruction:
    def test_url_includes_port_and_path(self):
        ssh = _make_ssh(stdout="200 0.005")
        check_app_health(ssh, port=8888, health_path="/readyz")
        cmd_arg = ssh.run.call_args[0][0]
        assert "8888" in cmd_arg
        assert "/readyz" in cmd_arg

    def test_url_uses_loopback_address(self):
        ssh = _make_ssh(stdout="200 0.005")
        check_app_health(ssh, port=3000, health_path="/health")
        cmd_arg = ssh.run.call_args[0][0]
        assert "127.0.0.1" in cmd_arg

    def test_path_with_query_string_is_included(self):
        ssh = _make_ssh(stdout="200 0.010")
        check_app_health(ssh, port=3000, health_path="/health?verbose=true")
        cmd_arg = ssh.run.call_args[0][0]
        assert "verbose=true" in cmd_arg


# ---------------------------------------------------------------------------
# Response time measurement
# ---------------------------------------------------------------------------


class TestResponseTimeMeasurement:
    def test_response_time_is_converted_from_seconds_to_ms(self):
        # curl reports 0.123 seconds → 123 ms
        ssh = _make_ssh(stdout="200 0.123")
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["response_time_ms"] == pytest.approx(123.0, abs=0.5)

    def test_response_time_is_rounded_to_one_decimal(self):
        ssh = _make_ssh(stdout="200 0.1234567")
        result = check_app_health(ssh, port=3000, health_path="/health")
        # Should be rounded to 1 decimal place
        assert result["response_time_ms"] == round(result["response_time_ms"], 1)

    def test_zero_response_time_is_valid(self):
        ssh = _make_ssh(stdout="200 0.000")
        result = check_app_health(ssh, port=3000, health_path="/health")
        assert result["response_time_ms"] == 0.0
