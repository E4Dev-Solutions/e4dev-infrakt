"""Docker Compose deployment engine for remote apps."""

from __future__ import annotations

import json
import re
import shlex
from collections.abc import Callable
from datetime import datetime
from pathlib import PurePosixPath

from cli.core.exceptions import DeploymentError
from cli.core.ssh import SSHClient

APP_BASE = PurePosixPath("/opt/infrakt/apps")

# Allow only safe characters in app names, branches, and image references
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_SAFE_BRANCH_RE = re.compile(r"^[a-zA-Z0-9._/-]+$")


def _validate_name(value: str, label: str) -> None:
    if not _SAFE_NAME_RE.match(value):
        raise DeploymentError(
            f"Invalid {label}: {value!r}. "
            "Only alphanumeric characters, dots, hyphens, and underscores are allowed."
        )


def _app_dir(app_name: str) -> str:
    _validate_name(app_name, "app name")
    return str(APP_BASE / app_name)


def deploy_app(
    ssh: SSHClient,
    app_name: str,
    *,
    git_repo: str | None = None,
    branch: str = "main",
    image: str | None = None,
    port: int = 3000,
    env_content: str = "",
    compose_override: str | None = None,
    log_fn: Callable[[str], None] | None = None,
) -> str:
    """Deploy or redeploy an app on a remote server.

    Returns deployment log string.  If *log_fn* is provided it is called with
    each log line as it is produced, enabling real-time streaming.
    """
    app_path = _app_dir(app_name)
    log_lines: list[str] = []

    def _log(msg: str) -> None:
        line = f"[{datetime.utcnow().isoformat()}] {msg}"
        log_lines.append(line)
        if log_fn is not None:
            log_fn(line)

    # Validate inputs
    if branch and not _SAFE_BRANCH_RE.match(branch):
        raise DeploymentError(f"Invalid branch name: {branch!r}")

    _log(f"Starting deployment of '{app_name}'")

    # Create app directory
    ssh.run_checked(f"mkdir -p {shlex.quote(app_path)}")

    # Write .env file
    if env_content:
        ssh.upload_string(env_content, f"{app_path}/.env")
        _log("Uploaded .env")

    # Handle git-based deployment
    if git_repo:
        repo_path = f"{app_path}/repo"
        q_repo = shlex.quote(repo_path)
        q_branch = shlex.quote(branch)
        q_git_repo = shlex.quote(git_repo)
        q_app_path = shlex.quote(app_path)

        _, _, code = ssh.run(f"test -d {q_repo}/.git")
        if code == 0:
            _log("Pulling latest changes")
            ssh.run_checked(
                f"cd {q_repo} && git fetch origin && git reset --hard origin/{q_branch}",
                timeout=120,
            )
        else:
            _log(f"Cloning {git_repo} (branch: {branch})")
            ssh.run_checked(
                f"git clone -b {q_branch} {q_git_repo} {q_repo}",
                timeout=120,
            )

        # Use compose file from repo if it exists, otherwise generate one
        _, _, has_compose = ssh.run(f"test -f {q_repo}/docker-compose.yml")
        if has_compose == 0 and not compose_override:
            _log("Using docker-compose.yml from repository")
            ssh.run_checked(
                f"cd {q_repo} && docker compose --env-file {q_app_path}/.env "
                f"up -d --build --remove-orphans",
                timeout=600,
            )
        else:
            compose_content = compose_override or _generate_compose(
                app_name, port=port, build_context="./repo"
            )
            ssh.upload_string(compose_content, f"{app_path}/docker-compose.yml")
            _log("Generated docker-compose.yml")
            ssh.run_checked(
                f"cd {q_app_path} && docker compose up -d --build --remove-orphans",
                timeout=600,
            )

    # Handle image-based deployment
    elif image:
        q_app_path = shlex.quote(app_path)
        compose_content = compose_override or _generate_compose(app_name, port=port, image=image)
        ssh.upload_string(compose_content, f"{app_path}/docker-compose.yml")
        _log(f"Deploying image: {image}")
        ssh.run_checked(
            f"cd {q_app_path} && docker compose up -d --pull always --remove-orphans",
            timeout=300,
        )

    # Handle compose-override-only deployment
    elif compose_override:
        q_app_path = shlex.quote(app_path)
        ssh.upload_string(compose_override, f"{app_path}/docker-compose.yml")
        _log("Using provided compose override")
        ssh.run_checked(
            f"cd {q_app_path} && docker compose up -d --remove-orphans",
            timeout=300,
        )

    else:
        raise DeploymentError(
            f"No deployment source specified for '{app_name}'. "
            "Provide --git, --image, or a compose file."
        )

    _log("Deployment complete")
    return "\n".join(log_lines)


def stop_app(ssh: SSHClient, app_name: str) -> None:
    app_path = _app_dir(app_name)
    ssh.run_checked(f"cd {shlex.quote(app_path)} && docker compose down", timeout=60)


def restart_app(ssh: SSHClient, app_name: str) -> None:
    app_path = _app_dir(app_name)
    ssh.run_checked(f"cd {shlex.quote(app_path)} && docker compose restart", timeout=60)


def destroy_app(ssh: SSHClient, app_name: str) -> None:
    app_path = _app_dir(app_name)
    q = shlex.quote(app_path)
    ssh.run(f"cd {q} && docker compose down -v --remove-orphans", timeout=60)
    ssh.run_checked(f"rm -rf {q}")


def get_logs(ssh: SSHClient, app_name: str, lines: int = 100) -> str:
    app_path = _app_dir(app_name)
    lines = max(1, min(lines, 10000))  # clamp to sane range
    ssh_cmd = f"cd {shlex.quote(app_path)} && docker compose logs --tail={int(lines)} --no-color"
    stdout = ssh.run_checked(ssh_cmd, timeout=30)
    return stdout


def _generate_compose(
    app_name: str,
    *,
    port: int = 3000,
    image: str | None = None,
    build_context: str | None = None,
) -> str:
    """Generate a minimal docker-compose.yml for an app."""
    _validate_name(app_name, "app name")
    port_var = app_name.upper().replace("-", "_") + "_PORT"

    lines = [
        f"# Generated by infrakt for app: {app_name}",
        "services:",
        f"  {app_name}:",
    ]
    if image:
        lines.append(f"    image: {image}")
    elif build_context:
        lines.append(f"    build: {build_context}")

    lines.extend(
        [
            f"    container_name: infrakt-{app_name}",
            "    restart: unless-stopped",
            "    env_file:",
            "      - .env",
            "    ports:",
            f'      - "127.0.0.1:${{{port_var}:-{port}}}:{port}"',
            "    networks:",
            "      - infrakt",
            "",
            "networks:",
            "  infrakt:",
            "    name: infrakt",
            "    external: true",
        ]
    )
    return "\n".join(lines) + "\n"


def get_container_health(ssh: SSHClient, app_name: str) -> list[dict[str, str]]:
    """Query real container state for an app using docker compose ps.

    Returns a list of dicts with keys: name, state, status, image, health.
    Returns empty list if the app directory doesn't exist or Docker is not running.
    """
    app_path = _app_dir(app_name)
    q = shlex.quote(app_path)

    # docker compose ps --format json outputs NDJSON (one JSON object per line)
    stdout, _, exit_code = ssh.run(
        f"cd {q} && docker compose ps --format json 2>/dev/null",
        timeout=15,
    )
    if exit_code != 0 or not stdout.strip():
        return []

    containers: list[dict[str, str]] = []
    for line in stdout.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            containers.append(
                {
                    "name": obj.get("Name", ""),
                    "state": obj.get("State", ""),
                    "status": obj.get("Status", ""),
                    "image": obj.get("Image", ""),
                    "health": obj.get("Health", ""),
                }
            )
        except json.JSONDecodeError:
            continue
    return containers


def reconcile_app_status(ssh: SSHClient, app_name: str) -> str:
    """Check actual Docker state and return the appropriate DB status string.

    Possible returns: "running", "stopped", "error", "restarting".
    """
    containers = get_container_health(ssh, app_name)
    if not containers:
        return "stopped"
    states = [c["state"] for c in containers]
    if any(s == "restarting" for s in states):
        return "restarting"
    if all(s == "running" for s in states):
        return "running"
    if any(s == "running" for s in states):
        return "error"  # partially running
    return "stopped"
