from unittest.mock import MagicMock

from cli.core.deployer import (
    _generate_compose,
    deploy_app,
    get_container_health,
    reconcile_app_status,
)


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
    assert "Starting deployment" in result
    assert "Deployment complete" in result


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
