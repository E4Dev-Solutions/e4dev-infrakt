from unittest.mock import MagicMock

from cli.core.deployer import _generate_compose, deploy_app


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
