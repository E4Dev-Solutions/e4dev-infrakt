"""Docker Compose deployment engine for remote apps."""

from __future__ import annotations

import json
import logging
import re
import shlex
import time
from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import datetime
from pathlib import PurePosixPath
from typing import Any

import yaml

from cli.core.exceptions import DeploymentError
from cli.core.github import get_github_token, inject_token_in_url
from cli.core.health import check_app_health
from cli.core.ssh import SSHClient

APP_BASE = PurePosixPath("/opt/infrakt/apps")

# Allow only safe characters in app names, branches, and image references
_SAFE_NAME_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]*$")
_SAFE_BRANCH_RE = re.compile(r"^[a-zA-Z0-9._/-]+$")
_SAFE_COMMIT_RE = re.compile(r"^[0-9a-f]{7,40}$")


@dataclass
class DeployResult:
    """Result of a deploy_app() call with captured metadata."""

    log: str = ""
    commit_hash: str | None = None
    image_used: str | None = None
    image_tag: str | None = None
    uses_repo_compose: bool = False


def _validate_name(value: str, label: str) -> None:
    if not _SAFE_NAME_RE.match(value):
        raise DeploymentError(
            f"Invalid {label}: {value!r}. "
            "Only alphanumeric characters, dots, hyphens, and underscores are allowed."
        )


def _app_dir(app_name: str) -> str:
    _validate_name(app_name, "app name")
    return str(APP_BASE / app_name)


def _compose_cmd(app_name: str) -> str:
    """Return ``docker compose -p <project>`` with a predictable project name.

    This ensures containers are named ``infrakt-{app_name}-{service}-1``
    regardless of the working directory, so Traefik can route to them by name.
    """
    return f"docker compose -p infrakt-{shlex.quote(app_name)}"


def _compose_work_dir(ssh: SSHClient, app_name: str) -> str:
    """Return the directory containing docker-compose.yml for this app.

    For repo-based apps the compose file lives in ``repo/``, not the app root.
    """
    app_path = _app_dir(app_name)
    repo_compose = f"{app_path}/repo/docker-compose.yml"
    _, _, rc = ssh.run(f"test -f {shlex.quote(repo_compose)}")
    if rc == 0:
        return f"{app_path}/repo"
    return app_path


def detect_primary_service(ssh: SSHClient, app_name: str) -> str | None:
    """Return the name of the primary routable service in a repo compose file.

    Inspects ``docker compose config`` for the first service that has a
    ``build`` directive or exposes ports (i.e. not a database).  Returns
    ``None`` if the compose file cannot be parsed.
    """
    work_dir = _compose_work_dir(ssh, app_name)
    cmd = f"cd {shlex.quote(work_dir)} && {_compose_cmd(app_name)} config --services"
    stdout, _, rc = ssh.run(cmd, timeout=15)
    if rc != 0 or not stdout.strip():
        return None
    services = [s.strip() for s in stdout.strip().splitlines() if s.strip()]
    if len(services) == 1:
        return services[0]

    # Multiple services — read full config to pick the primary one
    cmd2 = f"cd {shlex.quote(work_dir)} && {_compose_cmd(app_name)} config"
    stdout2, _, rc2 = ssh.run(cmd2, timeout=15)
    if rc2 != 0 or not stdout2.strip():
        return services[0]
    try:
        config = yaml.safe_load(stdout2)
    except Exception:
        return services[0]

    svc_defs = (config or {}).get("services", {})
    # Prefer a service with a build context (the app itself, not a DB image)
    for svc_name in services:
        svc_def = svc_defs.get(svc_name, {})
        if svc_def and svc_def.get("build") and not _classify_db_image(svc_def.get("image", "")):
            return svc_name
    # Fallback: first service with ports/expose
    for svc_name in services:
        svc_def = svc_defs.get(svc_name, {})
        if svc_def and (svc_def.get("ports") or svc_def.get("expose")):
            return svc_name
    return services[0]


def _connect_to_infrakt_network(
    ssh: SSHClient,
    app_name: str,
    q_repo: str,
    q_app_path: str,
    _log: Callable[[str], None],
) -> None:
    """Connect all containers of a repo-compose app to the ``infrakt`` network.

    Repo-based apps use the repository's own docker-compose.yml which typically
    doesn't declare the ``infrakt`` external network.  Without this step the
    containers end up on a project-default network and cannot reach Traefik,
    databases, or other infrakt-managed services.
    """
    compose = _compose_cmd(app_name)
    stdout, _, rc = ssh.run(
        f"cd {q_repo} && {compose} --env-file {q_app_path}/.env ps -q",
        timeout=15,
    )
    if rc != 0 or not stdout.strip():
        return
    for cid in stdout.strip().splitlines():
        cid = cid.strip()
        if not cid:
            continue
        # Silently skip if already connected (exit code 1 with "already exists")
        ssh.run(f"docker network connect infrakt {cid} 2>/dev/null || true")
    _log("Connected containers to infrakt network")


def deploy_app(
    ssh: SSHClient,
    app_name: str,
    *,
    git_repo: str | None = None,
    branch: str = "main",
    image: str | None = None,
    port: int = 3000,
    domain: str | None = None,
    env_content: str = "",
    compose_override: str | None = None,
    log_fn: Callable[[str], None] | None = None,
    pinned_commit: str | None = None,
    cpu_limit: str | None = None,
    memory_limit: str | None = None,
    replicas: int = 1,
    deploy_strategy: str = "restart",
    health_check_url: str | None = None,
    health_check_interval: int | None = None,
    build_type: str = "auto",
    deployment_id: int | None = None,
) -> DeployResult:
    """Deploy or redeploy an app on a remote server.

    Returns a DeployResult with log, commit_hash, and image_used.
    If *log_fn* is provided it is called with each log line as it is produced.
    If *pinned_commit* is provided (rollback), uses that commit instead of
    origin/{branch}.
    """
    app_path = _app_dir(app_name)
    log_lines: list[str] = []
    result = DeployResult()

    def _log(msg: str) -> None:
        line = f"[{datetime.utcnow().isoformat()}] {msg}"
        log_lines.append(line)
        if log_fn is not None:
            log_fn(line)

    def _stream(line: str) -> None:
        """Forward raw command output through log_fn."""
        log_lines.append(line)
        if log_fn is not None:
            log_fn(line)

    # Validate inputs
    if branch and not _SAFE_BRANCH_RE.match(branch):
        raise DeploymentError(f"Invalid branch name: {branch!r}")
    if pinned_commit and not _SAFE_COMMIT_RE.match(pinned_commit):
        raise DeploymentError(f"Invalid commit hash: {pinned_commit!r}")

    _log(f"Starting deployment of '{app_name}'")

    # Create app directory
    ssh.run_checked(f"mkdir -p {shlex.quote(app_path)}")

    # Write .env file (create empty one if no env vars so --env-file doesn't fail)
    ssh.upload_string(env_content or "", f"{app_path}/.env")
    if env_content:
        _log("Uploaded .env")

    # Handle git-based deployment
    if git_repo:
        # Inject GitHub PAT if available for private repo support
        _token = get_github_token()
        if _token:
            git_repo = inject_token_in_url(git_repo, _token)

        repo_path = f"{app_path}/repo"
        q_repo = shlex.quote(repo_path)
        q_branch = shlex.quote(branch)
        q_git_repo = shlex.quote(git_repo)
        q_app_path = shlex.quote(app_path)

        _, _, code = ssh.run(f"test -d {q_repo}/.git")
        if code == 0:
            if pinned_commit:
                q_commit = shlex.quote(pinned_commit)
                _log(f"Rolling back to commit {pinned_commit}")
                ssh.run_streaming(
                    f"cd {q_repo} && git fetch origin && git reset --hard {q_commit}",
                    on_output=_stream,
                    timeout=120,
                )
            else:
                _log("Pulling latest changes")
                ssh.run_streaming(
                    f"cd {q_repo} && git fetch origin && git reset --hard origin/{q_branch}",
                    on_output=_stream,
                    timeout=120,
                )
        else:
            _log(f"Cloning {git_repo} (branch: {branch})")
            ssh.run_streaming(
                f"git clone -b {q_branch} {q_git_repo} {q_repo}",
                on_output=_stream,
                timeout=120,
            )

        # Capture the commit hash
        stdout = ssh.run_checked(f"cd {q_repo} && git rev-parse HEAD")
        result.commit_hash = stdout.strip()[:40]

        # Determine build strategy
        _, _, has_compose = ssh.run(f"test -f {q_repo}/docker-compose.yml")
        use_nixpacks = False
        if build_type == "nixpacks":
            use_nixpacks = True
        elif build_type == "auto" and has_compose != 0:
            _, _, has_dockerfile = ssh.run(f"test -f {q_repo}/Dockerfile")
            if has_dockerfile != 0:
                use_nixpacks = True

        if use_nixpacks:
            nixpacks_image = f"infrakt-{app_name}"
            _log("Building with Nixpacks...")
            ssh.run_streaming(
                f"nixpacks build {q_repo} --name {shlex.quote(nixpacks_image)}",
                on_output=_stream,
                timeout=600,
            )
            compose_content = compose_override or _generate_compose(
                app_name,
                port=port,
                image=nixpacks_image,
                cpu_limit=cpu_limit,
                memory_limit=memory_limit,
                replicas=replicas,
                deploy_strategy=deploy_strategy,
                health_check_url=health_check_url,
                health_check_interval=health_check_interval,
                domain=domain,
            )
            ssh.upload_string(compose_content, f"{app_path}/docker-compose.yml")
            _log("Swapping containers...")
            ssh.run_streaming(
                f"cd {q_app_path} && {_compose_cmd(app_name)} up -d --remove-orphans",
                on_output=_stream,
                timeout=120,
            )
        elif has_compose == 0 and not compose_override:
            result.uses_repo_compose = True
            _log("Using docker-compose.yml from repository")
            # Also place .env in repo/ so compose auto-loads it for
            # services that reference ${VAR} without explicit env_file.
            ssh.run(f"cp {q_app_path}/.env {q_repo}/.env 2>/dev/null || true")
            _log("Building images...")
            ssh.run_streaming(
                f"cd {q_repo} && {_compose_cmd(app_name)} --env-file {q_app_path}/.env build",
                on_output=_stream,
                timeout=600,
            )
            _log("Swapping containers...")
            ssh.run_streaming(
                f"cd {q_repo} && {_compose_cmd(app_name)}"
                f" --env-file {q_app_path}/.env"
                f" up -d --remove-orphans",
                on_output=_stream,
                timeout=120,
            )
            # Repo-compose containers land on a default network — connect
            # them to the shared 'infrakt' network so Traefik and other
            # infrakt services (databases, etc.) can reach them.
            _connect_to_infrakt_network(ssh, app_name, q_repo, q_app_path, _log)
        else:
            compose_content = compose_override or _generate_compose(
                app_name,
                port=port,
                build_context="./repo",
                cpu_limit=cpu_limit,
                memory_limit=memory_limit,
                replicas=replicas,
                deploy_strategy=deploy_strategy,
                health_check_url=health_check_url,
                health_check_interval=health_check_interval,
                domain=domain,
            )
            ssh.upload_string(compose_content, f"{app_path}/docker-compose.yml")
            _log("Generated docker-compose.yml")
            _log("Building images...")
            ssh.run_streaming(
                f"cd {q_app_path} && {_compose_cmd(app_name)} build",
                on_output=_stream,
                timeout=600,
            )
            _log("Swapping containers...")
            ssh.run_streaming(
                f"cd {q_app_path} && {_compose_cmd(app_name)} up -d --remove-orphans",
                on_output=_stream,
                timeout=120,
            )

    # Handle image-based deployment
    elif image:
        q_app_path = shlex.quote(app_path)
        compose_content = compose_override or _generate_compose(
            app_name,
            port=port,
            image=image,
            cpu_limit=cpu_limit,
            memory_limit=memory_limit,
            replicas=replicas,
            deploy_strategy=deploy_strategy,
            health_check_url=health_check_url,
            health_check_interval=health_check_interval,
            domain=domain,
        )
        ssh.upload_string(compose_content, f"{app_path}/docker-compose.yml")
        _log(f"Deploying image: {image}")
        ssh.run_streaming(
            f"cd {q_app_path} && {_compose_cmd(app_name)} up -d --pull always --remove-orphans",
            on_output=_stream,
            timeout=300,
        )
        result.image_used = image

    # Handle compose-override-only deployment
    elif compose_override:
        q_app_path = shlex.quote(app_path)
        ssh.upload_string(compose_override, f"{app_path}/docker-compose.yml")
        _log("Using provided compose override")
        ssh.run_streaming(
            f"cd {q_app_path} && {_compose_cmd(app_name)} up -d --remove-orphans",
            on_output=_stream,
            timeout=300,
        )

    else:
        raise DeploymentError(
            f"No deployment source specified for '{app_name}'. "
            "Provide --git, --image, or a compose file."
        )

    # Health check gating for rolling deploys
    if deploy_strategy == "rolling" and health_check_url:
        _log("Waiting for health check to pass...")
        max_retries = 10
        for attempt in range(max_retries):
            time.sleep(5)
            health_result = check_app_health(ssh, port, health_check_url)
            if health_result["healthy"]:
                _log(f"Health check passed (attempt {attempt + 1})")
                break
            _log(f"Health check pending... (attempt {attempt + 1}/{max_retries})")
        else:
            _log("Health check failed after all retries — rolling back")
            q_path = shlex.quote(app_path)
            ssh.run(f"cd {q_path} && {_compose_cmd(app_name)} down", timeout=60)
            raise DeploymentError(
                f"Rolling deploy of '{app_name}' failed health check after {max_retries} attempts"
            )

    # Tag image for rollback (git builds and nixpacks only)
    if git_repo and deployment_id:
        image_name = f"infrakt-{app_name}"
        tag = f"v{deployment_id}"
        try:
            ssh.run_checked(
                f"docker tag {shlex.quote(image_name)} {shlex.quote(image_name)}:{shlex.quote(tag)}"
            )
            result.image_tag = f"{image_name}:{tag}"
            _log(f"Tagged image as {image_name}:{tag}")
        except Exception:
            _log("Warning: could not tag image for rollback")

    _log("Deployment complete")
    result.log = "\n".join(log_lines)
    return result


def _prune_old_images(ssh: SSHClient, app_name: str, keep: int = 5) -> None:
    """Remove old rollback image tags, keeping the N most recent."""
    image_name = f"infrakt-{app_name}"
    stdout, _, rc = ssh.run(
        f"docker images {shlex.quote(image_name)}"
        f" --format '{{{{.Tag}}}}' | grep '^v' | sort -t v -k 2 -n"
    )
    if rc != 0 or not stdout.strip():
        return
    tags = [t.strip() for t in stdout.strip().splitlines() if t.strip()]
    if len(tags) <= keep:
        return
    for old_tag in tags[:-keep]:
        ssh.run(f"docker rmi {shlex.quote(image_name)}:{shlex.quote(old_tag)} 2>/dev/null || true")


def stop_app(ssh: SSHClient, app_name: str) -> None:
    work_dir = _compose_work_dir(ssh, app_name)
    ssh.run_checked(f"cd {shlex.quote(work_dir)} && {_compose_cmd(app_name)} down", timeout=60)


def restart_app(ssh: SSHClient, app_name: str) -> None:
    work_dir = _compose_work_dir(ssh, app_name)
    ssh.run_checked(f"cd {shlex.quote(work_dir)} && {_compose_cmd(app_name)} restart", timeout=60)


def destroy_app(ssh: SSHClient, app_name: str) -> None:
    work_dir = _compose_work_dir(ssh, app_name)
    app_path = _app_dir(app_name)
    ssh.run(
        f"cd {shlex.quote(work_dir)} && {_compose_cmd(app_name)} down -v --remove-orphans",
        timeout=60,
    )
    ssh.run_checked(f"rm -rf {shlex.quote(app_path)}")


def get_logs(ssh: SSHClient, app_name: str, lines: int = 100, service: str | None = None) -> str:
    work_dir = _compose_work_dir(ssh, app_name)
    lines = max(1, min(lines, 10000))  # clamp to sane range
    svc = f" {shlex.quote(service)}" if service else ""
    compose = _compose_cmd(app_name)
    ssh_cmd = f"cd {shlex.quote(work_dir)} && {compose} logs --tail={int(lines)} --no-color{svc}"
    stdout = ssh.run_checked(ssh_cmd, timeout=30)
    return stdout


def stream_logs(
    ssh: SSHClient, app_name: str, lines: int = 100, service: str | None = None
) -> Generator[str, None, None]:
    """Stream container logs in real time via ``docker compose logs -f``.

    Yields log lines as they arrive.  The caller controls the lifetime —
    breaking out of the generator closes the SSH channel.
    """
    work_dir = _compose_work_dir(ssh, app_name)
    lines = max(1, min(lines, 10000))
    svc = f" {shlex.quote(service)}" if service else ""
    compose = _compose_cmd(app_name)
    cmd = f"cd {shlex.quote(work_dir)} && {compose} logs -f --tail={int(lines)} --no-color{svc}"
    channel = ssh.exec_stream(cmd)
    buf = b""
    try:
        while not channel.closed:
            if channel.recv_ready():
                data = channel.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    yield line.decode(errors="replace")
            else:
                channel.settimeout(1.0)
                try:
                    data = channel.recv(4096)
                    if not data:
                        break
                    buf += data
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        yield line.decode(errors="replace")
                except TimeoutError:
                    continue
    finally:
        channel.close()


def list_services(ssh: SSHClient, app_name: str) -> list[str]:
    """Return compose service names for an app."""
    work_dir = _compose_work_dir(ssh, app_name)
    cmd = f"cd {shlex.quote(work_dir)} && {_compose_cmd(app_name)} config --services"
    stdout = ssh.run_checked(cmd, timeout=15)
    return [s.strip() for s in stdout.strip().splitlines() if s.strip()]


_logger = logging.getLogger(__name__)

# Well-known DB images → infrakt db type
_DB_IMAGE_PREFIXES: dict[str, str] = {
    "postgres": "postgres",
    "mysql": "mysql",
    "mariadb": "mysql",
    "redis": "redis",
    "mongo": "mongo",
    "bitnami/postgresql": "postgres",
    "bitnami/mysql": "mysql",
    "bitnami/redis": "redis",
    "bitnami/mongodb": "mongo",
}


def detect_db_services(ssh: SSHClient, app_name: str) -> dict[str, str]:
    """Parse deployed compose config and return ``{service_name: db_type}`` for DB services."""
    work_dir = _compose_work_dir(ssh, app_name)
    cmd = f"cd {shlex.quote(work_dir)} && {_compose_cmd(app_name)} config"
    stdout, _, rc = ssh.run(cmd, timeout=15)
    if rc != 0 or not stdout.strip():
        return {}
    try:
        config = yaml.safe_load(stdout)
    except Exception:
        return {}
    services = (config or {}).get("services", {})
    result: dict[str, str] = {}
    for svc_name, svc_def in services.items():
        image = (svc_def or {}).get("image", "")
        for prefix, db_type in _DB_IMAGE_PREFIXES.items():
            if image.startswith(prefix):
                result[svc_name] = db_type
                break
    return result


@dataclass
class DetectedService:
    """Info about a service detected from a compose file."""

    name: str
    role: str  # "web", "api", "worker", "db", "cache", "unknown"
    port: int | None = None
    db_type: str | None = None  # e.g. "postgres", "redis" — only for db/cache roles
    routable: bool = False  # True if on the infrakt network (externally reachable)


def detect_all_services(ssh: SSHClient, app_name: str) -> list[DetectedService]:
    """Parse the deployed compose config and classify every service.

    Returns a list of ``DetectedService`` with role, port, and routability
    info. This lets the UI auto-suggest domain-to-service mappings.
    """
    work_dir = _compose_work_dir(ssh, app_name)
    cmd = f"cd {shlex.quote(work_dir)} && {_compose_cmd(app_name)} config"
    stdout, _, rc = ssh.run(cmd, timeout=15)
    if rc != 0 or not stdout.strip():
        return []
    try:
        config = yaml.safe_load(stdout)
    except Exception:
        return []

    services = (config or {}).get("services", {})
    result: list[DetectedService] = []

    for svc_name, svc_def in services.items():
        if not svc_def:
            continue

        image = svc_def.get("image", "")
        has_build = bool(svc_def.get("build"))
        networks = set(svc_def.get("networks", {}).keys())
        routable = "infrakt" in networks

        # Detect exposed port from expose or ports
        port = _detect_port(svc_def)

        # Classify service
        db_type = _classify_db_image(image)
        if db_type:
            role = "cache" if db_type == "redis" else "db"
            result.append(
                DetectedService(
                    name=svc_name,
                    role=role,
                    port=port,
                    db_type=db_type,
                    routable=routable,
                )
            )
        elif has_build or (image and not db_type):
            role = _guess_app_role(svc_name, svc_def)
            result.append(
                DetectedService(
                    name=svc_name,
                    role=role,
                    port=port,
                    routable=routable,
                )
            )

    return result


def _classify_db_image(image: str) -> str | None:
    """Return db_type if image matches a known DB, else None."""
    for prefix, db_type in _DB_IMAGE_PREFIXES.items():
        if image.startswith(prefix):
            return db_type
    return None


def _detect_port(svc_def: dict[str, Any]) -> int | None:
    """Extract the first exposed/published port from a service definition."""
    # Check 'expose' first (preferred for compose services)
    expose = svc_def.get("expose", [])
    if expose:
        try:
            return int(str(expose[0]).split("/")[0])
        except (ValueError, IndexError):
            pass
    # Check 'ports' (host:container mappings)
    ports = svc_def.get("ports", [])
    for p in ports:
        if isinstance(p, dict):
            target = p.get("target")
            if target:
                return int(target)
        elif isinstance(p, str) and ":" in p:
            try:
                return int(p.rsplit(":", 1)[1].split("/")[0])
            except (ValueError, IndexError):
                pass
    # Check environment for common PORT variables
    env = svc_def.get("environment", {})
    if isinstance(env, dict):
        for key in ("PORT", "APP_PORT", "SERVER_PORT"):
            val = env.get(key)
            if val:
                try:
                    return int(val)
                except (ValueError, TypeError):
                    pass
    return None


_WEB_HINTS = {"web", "frontend", "app", "client", "ui", "next", "nuxt", "www"}
_API_HINTS = {"api", "server", "backend", "gateway", "graphql", "rest"}
_WORKER_HINTS = {"worker", "queue", "consumer", "cron", "scheduler", "job"}


def _guess_app_role(svc_name: str, svc_def: dict[str, Any]) -> str:
    """Heuristically classify a non-DB service as web, api, or worker."""
    name_lower = svc_name.lower()
    # Check service name first
    for hint in _WEB_HINTS:
        if hint in name_lower:
            return "web"
    for hint in _API_HINTS:
        if hint in name_lower:
            return "api"
    for hint in _WORKER_HINTS:
        if hint in name_lower:
            return "worker"
    # Check if it has exposed ports (likely web/api)
    if svc_def.get("expose") or svc_def.get("ports"):
        return "web"
    return "unknown"


def _generate_compose(
    app_name: str,
    *,
    port: int = 3000,
    image: str | None = None,
    build_context: str | None = None,
    cpu_limit: str | None = None,
    memory_limit: str | None = None,
    replicas: int = 1,
    deploy_strategy: str = "restart",
    health_check_url: str | None = None,
    health_check_interval: int | None = None,
    domain: str | None = None,
) -> str:
    """Generate a minimal docker-compose.yml for an app."""
    _validate_name(app_name, "app name")
    from cli.core.compose_renderer import render_app_compose

    return render_app_compose(
        app_name,
        port=port,
        image=image,
        build_context=build_context,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        replicas=replicas,
        deploy_strategy=deploy_strategy,
        health_check_url=health_check_url,
        health_check_interval=health_check_interval,
        expose_port=not domain,
    )


def get_container_health(ssh: SSHClient, app_name: str) -> list[dict[str, str]]:
    """Query real container state for an app using docker compose ps.

    Returns a list of dicts with keys: name, state, status, image, health.
    Returns empty list if the app directory doesn't exist or Docker is not running.
    """
    work_dir = _compose_work_dir(ssh, app_name)
    q = shlex.quote(work_dir)

    # docker compose ps --format json outputs NDJSON (one JSON object per line)
    stdout, _, exit_code = ssh.run(
        f"cd {q} && {_compose_cmd(app_name)} ps --format json 2>/dev/null",
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
