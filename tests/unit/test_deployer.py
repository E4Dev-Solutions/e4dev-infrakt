from unittest.mock import MagicMock

import pytest

from cli.core.deployer import (
    DeployResult,
    _generate_compose,
    deploy_app,
    get_container_health,
    reconcile_app_status,
    stream_logs,
)
from cli.core.exceptions import DeploymentError


def test_generate_compose_with_image():
    content = _generate_compose("my-api", port=8000, image="node:20")
    assert "image: node:20" in content
    assert "infrakt-my-api" in content
    assert "8000" in content


def test_generate_compose_with_build_context():
    content = _generate_compose("my-api", port=3000, build_context="./repo")
    assert "build: ./repo" in content
    assert "infrakt-my-api" in content


def test_deploy_app_calls_log_fn():
    """Verify that log_fn callback receives log lines during deployment."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.run_checked = MagicMock(return_value="")
    ssh.run = MagicMock(return_value=("", "", 0))
    ssh.upload_string = MagicMock()

    received: list[str] = []
    deploy_app(
        ssh,
        "test-app",
        image="nginx:latest",
        log_fn=received.append,
    )
    assert len(received) > 0
    assert any("Starting deployment" in line for line in received)
    assert any("Deployment complete" in line for line in received)


def test_deploy_app_without_log_fn():
    """Verify that deploy_app works without log_fn (backward compat)."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.run_checked = MagicMock(return_value="")
    ssh.run = MagicMock(return_value=("", "", 0))
    ssh.upload_string = MagicMock()

    result = deploy_app(ssh, "test-app", image="nginx:latest")
    assert "Starting deployment" in result.log
    assert "Deployment complete" in result.log


# ── Health check tests ─────────────────────────────────────────────────────────


def test_get_container_health_parses_ndjson():
    ssh = MagicMock()
    ndjson = (
        '{"Name":"infrakt-myapp","State":"running",'
        '"Status":"Up 2 hours","Image":"nginx:latest","Health":""}\n'
    )
    ssh.run.return_value = (ndjson, "", 0)
    result = get_container_health(ssh, "myapp")
    assert len(result) == 1
    assert result[0]["name"] == "infrakt-myapp"
    assert result[0]["state"] == "running"
    assert result[0]["image"] == "nginx:latest"
    assert result[0]["health"] == ""


def test_get_container_health_returns_empty_on_nonzero_exit():
    ssh = MagicMock()
    ssh.run.return_value = ("", "compose not found", 1)
    result = get_container_health(ssh, "myapp")
    assert result == []


def test_get_container_health_handles_multiple_containers():
    ssh = MagicMock()
    ndjson = (
        '{"Name":"app","State":"running","Status":"Up","Image":"nginx","Health":"healthy"}\n'
        '{"Name":"db","State":"running","Status":"Up","Image":"postgres","Health":""}\n'
    )
    ssh.run.return_value = (ndjson, "", 0)
    result = get_container_health(ssh, "myapp")
    assert len(result) == 2
    assert result[0]["health"] == "healthy"


def test_reconcile_app_status_all_running():
    ssh = MagicMock()
    ssh.run.return_value = (
        '{"Name":"c1","State":"running","Status":"Up","Image":"x","Health":""}\n',
        "",
        0,
    )
    assert reconcile_app_status(ssh, "myapp") == "running"


def test_reconcile_app_status_all_exited():
    ssh = MagicMock()
    ssh.run.return_value = (
        '{"Name":"c1","State":"exited","Status":"Exited (1)","Image":"x","Health":""}\n',
        "",
        0,
    )
    assert reconcile_app_status(ssh, "myapp") == "stopped"


def test_reconcile_app_status_restarting():
    ssh = MagicMock()
    ssh.run.return_value = (
        '{"Name":"c1","State":"restarting","Status":"Restarting","Image":"x","Health":""}\n',
        "",
        0,
    )
    assert reconcile_app_status(ssh, "myapp") == "restarting"


def test_reconcile_app_status_partial_running():
    ssh = MagicMock()
    ndjson = (
        '{"Name":"app","State":"running","Status":"Up","Image":"x","Health":""}\n'
        '{"Name":"db","State":"exited","Status":"Exited","Image":"x","Health":""}\n'
    )
    ssh.run.return_value = (ndjson, "", 0)
    assert reconcile_app_status(ssh, "myapp") == "error"


def test_reconcile_app_status_no_containers():
    ssh = MagicMock()
    ssh.run.return_value = ("", "", 1)
    assert reconcile_app_status(ssh, "myapp") == "stopped"


# ── DeployResult and metadata capture tests ───────────────────────────────────


def test_deploy_app_returns_deploy_result():
    """deploy_app returns a DeployResult with image_used for image deploys."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.run_checked = MagicMock(return_value="")
    ssh.run = MagicMock(return_value=("", "", 0))
    ssh.upload_string = MagicMock()

    result = deploy_app(ssh, "test-app", image="nginx:1.25")
    assert isinstance(result, DeployResult)
    assert result.image_used == "nginx:1.25"
    assert result.commit_hash is None
    assert "Deployment complete" in result.log


def test_deploy_app_captures_commit_hash_for_git():
    """deploy_app captures git commit hash after clone/pull."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    # test -d returns 1 (no existing repo -> clone)
    ssh.run = MagicMock(side_effect=[("", "", 1), ("", "", 1)])
    ssh.run_checked = MagicMock(
        side_effect=[
            "",  # mkdir
            "",  # git clone
            "abc123def456\n",  # git rev-parse HEAD
            "",  # docker compose up
        ]
    )

    result = deploy_app(ssh, "test-app", git_repo="https://github.com/test/repo.git", branch="main")
    assert isinstance(result, DeployResult)
    assert result.commit_hash == "abc123def456"
    assert result.image_used is None


def test_deploy_app_pinned_commit_uses_reset():
    """pinned_commit triggers git reset --hard <commit> instead of origin/branch."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    # test -d returns 0 (existing repo -> pull/reset)
    ssh.run = MagicMock(side_effect=[("", "", 0), ("", "", 1)])
    ssh.run_checked = MagicMock(
        side_effect=[
            "",  # mkdir
            "",  # git fetch + reset --hard <commit>
            "deadbeef12345678\n",  # git rev-parse HEAD
            "",  # docker compose up
        ]
    )

    result = deploy_app(
        ssh,
        "test-app",
        git_repo="https://github.com/test/repo.git",
        branch="main",
        pinned_commit="deadbeef12345678",
    )

    # Verify it used the pinned commit in the reset command
    reset_call = ssh.run_checked.call_args_list[1]
    assert "deadbeef12345678" in reset_call[0][0]
    assert "origin/" not in reset_call[0][0]
    assert result.commit_hash == "deadbeef12345678"


def test_deploy_app_rejects_invalid_pinned_commit():
    """Invalid pinned_commit raises DeploymentError."""
    ssh = MagicMock()
    with pytest.raises(DeploymentError, match="Invalid commit hash"):
        deploy_app(
            ssh,
            "test-app",
            git_repo="https://github.com/test/repo.git",
            pinned_commit="not-a-valid-hash!",
        )


# ── stream_logs tests ─────────────────────────────────────────────────────────


def test_stream_logs_yields_lines():
    """stream_logs yields decoded lines from the SSH channel."""
    ssh = MagicMock()
    channel = MagicMock()

    # Simulate two recv calls: first returns two lines, second raises to end loop
    call_count = 0

    def fake_recv(size):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return b"line-one\nline-two\n"
        # End the stream
        return b""

    channel.closed = False
    channel.recv_ready.return_value = True
    channel.recv = fake_recv
    ssh.exec_stream = MagicMock(return_value=channel)

    lines = list(stream_logs(ssh, "myapp", lines=50))
    assert lines == ["line-one", "line-two"]
    channel.close.assert_called_once()


def test_stream_logs_handles_partial_lines():
    """stream_logs buffers partial lines until a newline arrives."""
    ssh = MagicMock()
    channel = MagicMock()

    call_count = 0

    def fake_recv(size):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return b"partial"
        if call_count == 2:
            return b"-complete\n"
        return b""

    channel.closed = False
    channel.recv_ready.return_value = True
    channel.recv = fake_recv
    ssh.exec_stream = MagicMock(return_value=channel)

    lines = list(stream_logs(ssh, "myapp"))
    assert lines == ["partial-complete"]
    channel.close.assert_called_once()
