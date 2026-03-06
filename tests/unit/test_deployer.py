from unittest.mock import MagicMock, patch

import pytest

from cli.core.deployer import (
    DeployResult,
    _compose_work_dir,
    _generate_compose,
    deploy_app,
    detect_all_services,
    detect_db_services,
    detect_primary_service,
    get_container_health,
    get_logs,
    list_services,
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
    ssh.run_streaming = MagicMock(return_value="")
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
    ssh.run_streaming = MagicMock(return_value="")
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
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run = MagicMock(return_value=("", "", 0))
    ssh.upload_string = MagicMock()

    result = deploy_app(ssh, "test-app", image="nginx:1.25")
    assert isinstance(result, DeployResult)
    assert result.image_used == "nginx:1.25"
    assert result.commit_hash is None
    assert "Deployment complete" in result.log


@patch("cli.core.deployer.get_github_token", return_value=None)
def test_deploy_app_captures_commit_hash_for_git(_mock_token):
    """deploy_app captures git commit hash after clone/pull."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    ssh.run = MagicMock(side_effect=[
        ("", "", 1),                       # test -d repo
        ("feat: test commit\n", "", 0),    # git log msg
        ("", "", 1),                       # test -f compose
        ("", "", 1),                       # test -f Dockerfile
    ])
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run_checked = MagicMock(
        side_effect=[
            "",  # mkdir
            "abc123def456\n",  # git rev-parse HEAD
        ]
    )

    result = deploy_app(ssh, "test-app", git_repo="https://github.com/test/repo.git", branch="main")
    assert isinstance(result, DeployResult)
    assert result.commit_hash == "abc123def456"
    assert result.commit_message == "feat: test commit"
    assert result.image_used is None


@patch("cli.core.deployer.get_github_token", return_value=None)
def test_deploy_app_pinned_commit_uses_reset(_mock_token):
    """pinned_commit triggers git reset --hard <commit> instead of origin/branch."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    ssh.run = MagicMock(side_effect=[
        ("", "", 0),                    # test -d repo
        ("fix: something\n", "", 0),    # git log msg
        ("", "", 1),                    # test -f compose
        ("", "", 1),                    # test -f Dockerfile
    ])
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run_checked = MagicMock(
        side_effect=[
            "",  # mkdir
            "deadbeef12345678\n",  # git rev-parse HEAD
        ]
    )

    result = deploy_app(
        ssh,
        "test-app",
        git_repo="https://github.com/test/repo.git",
        branch="main",
        pinned_commit="deadbeef12345678",
    )

    # Verify it used the pinned commit in the streaming command
    reset_call = ssh.run_streaming.call_args_list[0]
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
    ssh.run = MagicMock(return_value=("", "", 1))  # no repo compose
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
    ssh.run = MagicMock(return_value=("", "", 1))  # no repo compose
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


# ── GitHub token injection tests ──────────────────────────────────────────────


# ── Image tagging for rollback tests ─────────────────────────────────────────


@patch("cli.core.deployer.get_github_token", return_value=None)
def test_deploy_git_tags_image_after_build(_mock_token):
    """After a successful git build, the image should be tagged for rollback."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    ssh.run = MagicMock(side_effect=[
        ("", "", 1),          # test -d repo
        ("msg\n", "", 0),     # git log msg
        ("", "", 1),          # test -f compose
        ("", "", 1),          # test -f Dockerfile
        ("", "", 1),          # prune images
    ])
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run_checked = MagicMock(side_effect=["", "abc1234567890\n", ""])

    result = deploy_app(
        ssh,
        "test-app",
        git_repo="https://github.com/test/repo.git",
        branch="main",
        deployment_id=42,
    )

    tag_cmds = [str(c) for c in ssh.run_checked.call_args_list if "docker tag" in str(c)]
    assert len(tag_cmds) == 1
    assert "infrakt-test-app:v42" in tag_cmds[0]
    assert result.image_tag == "infrakt-test-app:v42"


@patch("cli.core.deployer.get_github_token", return_value=None)
def test_deploy_git_no_tag_without_deployment_id(_mock_token):
    """Without deployment_id, no image tagging occurs."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    ssh.run = MagicMock(side_effect=[("", "", 1), ("msg\n", "", 0), ("", "", 1), ("", "", 1)])
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run_checked = MagicMock(side_effect=["", "abc1234567890\n"])

    result = deploy_app(
        ssh,
        "test-app",
        git_repo="https://github.com/test/repo.git",
        branch="main",
    )

    tag_cmds = [str(c) for c in ssh.run_checked.call_args_list if "docker tag" in str(c)]
    assert len(tag_cmds) == 0
    assert result.image_tag is None


# ── Nixpacks build tests ─────────────────────────────────────────────────────


@patch("cli.core.deployer.get_github_token", return_value=None)
def test_deploy_git_nixpacks_builds_with_nixpacks(_mock_token):
    """When build_type=nixpacks, deployer runs nixpacks build instead of docker compose build."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    # test -d returns 1 (clone), git log (msg), test -f returns 1 (no compose)
    ssh.run = MagicMock(side_effect=[("", "", 1), ("msg\n", "", 0), ("", "", 1)])
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run_checked = MagicMock(side_effect=["", "abc1234567890\n"])

    deploy_app(
        ssh,
        "test-app",
        git_repo="https://github.com/test/repo.git",
        branch="main",
        build_type="nixpacks",
    )

    streaming_cmds = [str(c) for c in ssh.run_streaming.call_args_list]
    assert any("nixpacks build" in c for c in streaming_cmds)
    assert not any("compose" in c and " build" in c for c in streaming_cmds)


@patch("cli.core.deployer.get_github_token", return_value=None)
def test_deploy_git_auto_detects_nixpacks_when_no_dockerfile(_mock_token):
    """build_type=auto with no Dockerfile and no compose should use Nixpacks."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    ssh.run = MagicMock(side_effect=[
        ("", "", 1),          # test -d repo
        ("msg\n", "", 0),     # git log msg
        ("", "", 1),          # test -f compose
        ("", "", 1),          # test -f Dockerfile
    ])
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run_checked = MagicMock(side_effect=["", "abc1234567890\n"])

    deploy_app(
        ssh,
        "test-app",
        git_repo="https://github.com/test/repo.git",
        branch="main",
        build_type="auto",
    )

    streaming_cmds = [str(c) for c in ssh.run_streaming.call_args_list]
    assert any("nixpacks build" in c for c in streaming_cmds)


# ── Split build/swap tests ────────────────────────────────────────────────────


@patch("cli.core.deployer.get_github_token", return_value=None)
def test_deploy_git_splits_build_and_up(_mock_token):
    """Git deploys must call 'docker compose build' then 'docker compose up -d' separately."""
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.upload_string = MagicMock()
    # test -d (repo?) = 1, git log (msg), test -f (compose?) = 1
    ssh.run = MagicMock(side_effect=[("", "", 1), ("msg\n", "", 0), ("", "", 1)])
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run_checked = MagicMock(side_effect=["", "abc1234567890\n"])

    deploy_app(
        ssh,
        "test-app",
        git_repo="https://github.com/test/repo.git",
        branch="main",
        build_type="dockerfile",
    )

    streaming_cmds = [str(c) for c in ssh.run_streaming.call_args_list]
    # Should have: git clone, docker compose build, docker compose up
    assert any("git clone" in c for c in streaming_cmds)
    assert any("compose" in c and "build" in c and "up" not in c for c in streaming_cmds)
    assert any("compose" in c and "up -d" in c and "--build" not in c for c in streaming_cmds)


# ── Rolling deploy health check tests ─────────────────────────────────────────


@patch("cli.core.deployer.time.sleep")
@patch("cli.core.deployer.get_github_token", return_value=None)
@patch("cli.core.deployer.check_app_health")
def test_rolling_deploy_uses_http_health_check(mock_health, _mock_token, _mock_sleep):
    """Rolling deploy must call check_app_health, not reconcile_app_status."""
    mock_health.return_value = {
        "healthy": True,
        "status_code": 200,
        "response_time_ms": 50,
        "error": None,
    }
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.run_checked = MagicMock(return_value="")
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run = MagicMock(return_value=("", "", 0))
    ssh.upload_string = MagicMock()

    deploy_app(
        ssh,
        "test-app",
        image="nginx:latest",
        deploy_strategy="rolling",
        health_check_url="/health",
        port=3000,
    )

    mock_health.assert_called_once_with(ssh, 3000, "/health")


@patch("cli.core.deployer.time.sleep")
@patch("cli.core.deployer.get_github_token", return_value=None)
@patch("cli.core.deployer.check_app_health")
def test_rolling_deploy_fails_on_unhealthy(mock_health, _mock_token, _mock_sleep):
    """Rolling deploy raises DeploymentError when health check never passes."""
    mock_health.return_value = {
        "healthy": False,
        "status_code": 503,
        "response_time_ms": 100,
        "error": None,
    }
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.run_checked = MagicMock(return_value="")
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run = MagicMock(return_value=("", "", 0))
    ssh.upload_string = MagicMock()

    with pytest.raises(DeploymentError, match="failed health check"):
        deploy_app(
            ssh,
            "test-app",
            image="nginx:latest",
            deploy_strategy="rolling",
            health_check_url="/health",
            port=3000,
        )


@patch("cli.core.deployer.get_github_token")
def test_deploy_git_injects_token_for_github(mock_get_token):
    """When a GitHub PAT is stored, clone URL should include the token."""
    mock_get_token.return_value = "ghp_secret"
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.run_checked = MagicMock(return_value="abc1234567890")
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run = MagicMock(return_value=("", "", 1))  # no existing repo
    ssh.upload_string = MagicMock()

    deploy_app(ssh, "test-app", git_repo="https://github.com/org/repo.git", branch="main")

    clone_calls = [c for c in ssh.run_streaming.call_args_list if "git clone" in str(c)]
    assert len(clone_calls) == 1
    clone_cmd = str(clone_calls[0])
    assert "ghp_secret@github.com" in clone_cmd


@patch("cli.core.deployer.get_github_token")
def test_deploy_git_no_token_uses_plain_url(mock_get_token):
    """When no PAT is stored, clone URL should be used as-is."""
    mock_get_token.return_value = None
    ssh = MagicMock()
    ssh.__enter__ = MagicMock(return_value=ssh)
    ssh.__exit__ = MagicMock(return_value=False)
    ssh.run_checked = MagicMock(return_value="abc1234567890")
    ssh.run_streaming = MagicMock(return_value="")
    ssh.run = MagicMock(return_value=("", "", 1))  # no existing repo
    ssh.upload_string = MagicMock()

    deploy_app(ssh, "test-app", git_repo="https://github.com/org/repo.git", branch="main")

    clone_calls = [c for c in ssh.run_streaming.call_args_list if "git clone" in str(c)]
    assert len(clone_calls) == 1
    clone_cmd = str(clone_calls[0])
    assert "github.com/org/repo.git" in clone_cmd
    assert "@github.com" not in clone_cmd


# ── Compose work dir tests ──────────────────────────────────────────────────


def test_compose_work_dir_returns_repo_when_compose_exists_there():
    """_compose_work_dir returns repo/ subdir when it contains docker-compose.yml."""
    ssh = MagicMock()
    ssh.run = MagicMock(return_value=("", "", 0))  # test -f succeeds
    result = _compose_work_dir(ssh, "myapp")
    assert result == "/opt/infrakt/apps/myapp/repo"


def test_compose_work_dir_returns_app_dir_when_no_repo_compose():
    """_compose_work_dir returns app dir when repo/docker-compose.yml doesn't exist."""
    ssh = MagicMock()
    ssh.run = MagicMock(return_value=("", "", 1))  # test -f fails
    result = _compose_work_dir(ssh, "myapp")
    assert result == "/opt/infrakt/apps/myapp"


def test_get_logs_uses_compose_work_dir():
    """get_logs uses repo/ dir when compose file is there."""
    ssh = MagicMock()
    # First call: test -f repo/docker-compose.yml → 0 (exists)
    ssh.run = MagicMock(return_value=("", "", 0))
    ssh.run_checked = MagicMock(return_value="some logs")
    result = get_logs(ssh, "myapp", lines=50)
    cmd = ssh.run_checked.call_args[0][0]
    assert "/opt/infrakt/apps/myapp/repo" in cmd
    assert result == "some logs"


def test_list_services_uses_compose_work_dir():
    """list_services runs from repo/ dir when compose file is there."""
    ssh = MagicMock()
    ssh.run = MagicMock(return_value=("", "", 0))
    ssh.run_checked = MagicMock(return_value="web\ndb\n")
    result = list_services(ssh, "myapp")
    cmd = ssh.run_checked.call_args[0][0]
    assert "/opt/infrakt/apps/myapp/repo" in cmd
    assert result == ["web", "db"]


# ── Embedded DB detection tests ─────────────────────────────────────────────


def test_detect_db_services_finds_postgres_and_redis():
    """detect_db_services identifies DB services by their image prefix."""
    import yaml

    compose_config = yaml.dump(
        {
            "services": {
                "web": {"image": "node:20", "ports": ["3000:3000"]},
                "db": {"image": "postgres:16-alpine"},
                "cache": {"image": "redis:7-alpine"},
            }
        }
    )
    ssh = MagicMock()
    # test -f for _compose_work_dir
    ssh.run = MagicMock(
        side_effect=[
            ("", "", 1),  # no repo/docker-compose.yml
            (compose_config, "", 0),  # docker compose config output
        ]
    )
    result = detect_db_services(ssh, "myapp")
    assert result == {"db": "postgres", "cache": "redis"}
    assert "web" not in result


def test_detect_db_services_returns_empty_on_failure():
    """detect_db_services returns empty dict when compose config fails."""
    ssh = MagicMock()
    ssh.run = MagicMock(
        side_effect=[
            ("", "", 1),  # no repo/docker-compose.yml
            ("", "error", 1),  # compose config failed
        ]
    )
    result = detect_db_services(ssh, "myapp")
    assert result == {}


def test_detect_db_services_handles_bitnami_images():
    """detect_db_services recognises bitnami/* image prefixes."""
    import yaml

    compose_config = yaml.dump(
        {
            "services": {
                "app": {"image": "myapp:latest"},
                "postgres": {"image": "bitnami/postgresql:15"},
                "mongo": {"image": "bitnami/mongodb:7"},
            }
        }
    )
    ssh = MagicMock()
    ssh.run = MagicMock(
        side_effect=[
            ("", "", 1),
            (compose_config, "", 0),
        ]
    )
    result = detect_db_services(ssh, "myapp")
    assert result == {"postgres": "postgres", "mongo": "mongo"}


def test_detect_all_services_classifies_web_api_db():
    """detect_all_services classifies services by role and detects ports."""
    import yaml

    compose_config = yaml.dump(
        {
            "services": {
                "web": {
                    "build": {"context": ".", "dockerfile": "apps/web/Dockerfile"},
                    "expose": ["3000"],
                    "networks": {"infrakt": None, "internal": None},
                },
                "api": {
                    "build": {"context": ".", "dockerfile": "apps/api/Dockerfile"},
                    "expose": ["4000"],
                    "environment": {"PORT": "4000"},
                    "networks": {"infrakt": None, "internal": None},
                },
                "postgres": {
                    "image": "postgres:17-alpine",
                    "networks": {"internal": None},
                },
                "redis": {
                    "image": "redis:7-alpine",
                    "networks": {"internal": None},
                },
            }
        }
    )
    ssh = MagicMock()
    ssh.run = MagicMock(
        side_effect=[
            ("", "", 1),  # _compose_work_dir: no repo compose
            (compose_config, "", 0),  # docker compose config
        ]
    )
    services = detect_all_services(ssh, "myapp")
    by_name = {s.name: s for s in services}

    assert by_name["web"].role == "web"
    assert by_name["web"].port == 3000
    assert by_name["web"].routable is True

    assert by_name["api"].role == "api"
    assert by_name["api"].port == 4000
    assert by_name["api"].routable is True

    assert by_name["postgres"].role == "db"
    assert by_name["postgres"].db_type == "postgres"
    assert by_name["postgres"].routable is False

    assert by_name["redis"].role == "cache"
    assert by_name["redis"].db_type == "redis"
    assert by_name["redis"].routable is False


# ── detect_primary_service tests ─────────────────────────────────────────────


def test_detect_primary_service_single_service():
    """With one service, returns that service name."""
    ssh = MagicMock()
    # _compose_work_dir: test -f repo/docker-compose.yml → exists
    ssh.run = MagicMock(
        side_effect=[
            ("", "", 0),  # _compose_work_dir
            ("app\n", "", 0),  # config --services
        ]
    )
    result = detect_primary_service(ssh, "myapp")
    assert result == "app"


def test_detect_primary_service_picks_build_service():
    """With multiple services, prefers one with a build directive."""
    import yaml

    config = yaml.dump(
        {
            "services": {
                "db": {"image": "postgres:16"},
                "app": {"build": {"context": "."}, "ports": ["3000:3000"]},
            }
        }
    )
    ssh = MagicMock()
    ssh.run = MagicMock(
        side_effect=[
            ("", "", 0),  # _compose_work_dir
            ("db\napp\n", "", 0),  # config --services
            (config, "", 0),  # config (full)
        ]
    )
    result = detect_primary_service(ssh, "myapp")
    assert result == "app"


def test_detect_primary_service_picks_port_service_as_fallback():
    """Falls back to service with ports when no build directive."""
    import yaml

    config = yaml.dump(
        {
            "services": {
                "worker": {"image": "myworker:latest"},
                "web": {"image": "myweb:latest", "ports": ["8080:8080"]},
            }
        }
    )
    ssh = MagicMock()
    ssh.run = MagicMock(
        side_effect=[
            ("", "", 0),  # _compose_work_dir
            ("worker\nweb\n", "", 0),  # config --services
            (config, "", 0),  # config (full)
        ]
    )
    result = detect_primary_service(ssh, "myapp")
    assert result == "web"


def test_detect_primary_service_returns_none_on_failure():
    """Returns None when compose commands fail."""
    ssh = MagicMock()
    ssh.run = MagicMock(
        side_effect=[
            ("", "", 0),  # _compose_work_dir
            ("", "", 1),  # config --services fails
        ]
    )
    result = detect_primary_service(ssh, "myapp")
    assert result is None


# ── Network connection tests ─────────────────────────────────────────────────


@patch("cli.core.deployer.get_github_token", return_value=None)
def test_deploy_repo_compose_connects_to_infrakt_network(_mock_token):
    """Repo-compose deploy connects containers to the infrakt network."""
    ssh = MagicMock()
    ssh.run = MagicMock(return_value=("", "", 0))
    ssh.run_checked = MagicMock(return_value="abc1234" + "0" * 33)
    ssh.run_streaming = MagicMock()
    ssh.upload_string = MagicMock()

    # After compose up, ps -q returns container IDs
    container_ids = "abc123\ndef456\n"

    def smart_run(cmd, **kwargs):
        if "ps -q" in cmd:
            return (container_ids, "", 0)
        return ("", "", 0)

    ssh.run = MagicMock(side_effect=smart_run)
    ssh.run_checked = MagicMock(return_value="abc1234" + "0" * 33)

    result = deploy_app(
        ssh,
        "myapp",
        git_repo="https://github.com/test/repo.git",
        branch="main",
        port=3000,
    )
    assert result.uses_repo_compose is True

    # Verify docker network connect was called for each container
    network_connect_calls = [
        call for call in ssh.run.call_args_list if "docker network connect infrakt" in str(call)
    ]
    assert len(network_connect_calls) >= 2
