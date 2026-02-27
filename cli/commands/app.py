from datetime import datetime

import click

from cli.core.app_templates import (
    APP_TEMPLATES,
    get_template,
    list_templates,
    render_template_compose,
)
from cli.core.console import console, error, info, print_table, status_spinner, success
from cli.core.crypto import env_content_for_app
from cli.core.database import get_session, init_db
from cli.core.deployer import (
    deploy_app,
    destroy_app,
    get_container_health,
    get_logs,
    reconcile_app_status,
    restart_app,
    stop_app,
)
from cli.core.exceptions import AppNotFoundError, ServerNotFoundError
from cli.core.proxy_manager import add_domain, remove_domain
from cli.core.ssh import SSHClient
from cli.models.app import App
from cli.models.app_dependency import AppDependency
from cli.models.deployment import Deployment
from cli.models.server import Server


def _resolve_server(
    session: object, server_name: str | None, app_name: str | None = None
) -> Server:
    """Resolve server by name, or by looking up the app's server."""
    if server_name:
        srv: Server | None = session.query(Server).filter(Server.name == server_name).first()  # type: ignore[attr-defined]
        if not srv:
            raise ServerNotFoundError(f"Server '{server_name}' not found")
        return srv
    if app_name:
        app_obj: App | None = session.query(App).filter(App.name == app_name).first()  # type: ignore[attr-defined]
        if app_obj:
            return app_obj.server
    raise click.UsageError("Please specify --server or ensure the app name is unique")


def _get_app(session: object, app_name: str, server_name: str | None) -> App:
    q = session.query(App).filter(App.name == app_name)  # type: ignore[attr-defined]
    if server_name:
        q = q.join(Server).filter(Server.name == server_name)
    app_obj: App | None = q.first()
    if not app_obj:
        raise AppNotFoundError(f"App '{app_name}' not found")
    return app_obj


def _ssh_for_server(srv: Server) -> SSHClient:
    result = SSHClient.from_server(srv)
    return result


@click.group()
def app() -> None:
    """Manage application deployments."""


@app.command()
@click.option("--server", "server_name", required=True, help="Target server name")
@click.option("--name", required=True, help="App name")
@click.option("--domain", default=None, help="Domain for the app (e.g. api.example.com)")
@click.option("--port", default=None, type=int, help="Container port the app listens on")
@click.option("--git", "git_repo", default=None, help="Git repository URL")
@click.option("--branch", default="main", help="Git branch")
@click.option("--image", default=None, help="Docker image (e.g. nginx:latest)")
@click.option("--replicas", default=1, type=int, help="Number of replicas")
@click.option(
    "--template",
    "template_name",
    default=None,
    help="Built-in template (nginx, uptime-kuma, n8n, docmost, devtools)",
)
def create(
    server_name: str,
    name: str,
    domain: str | None,
    port: int | None,
    git_repo: str | None,
    branch: str,
    image: str | None,
    replicas: int,
    template_name: str | None,
) -> None:
    """Create a new app on a server."""
    init_db()

    # Validate template if provided
    tmpl = None
    if template_name:
        tmpl = get_template(template_name)
        if not tmpl:
            error(f"Unknown template '{template_name}'. Use 'infrakt app templates' to list.")
            raise SystemExit(1)

    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server_name).first()
        if not srv:
            error(f"Server '{server_name}' not found")
            raise SystemExit(1)

        existing = session.query(App).filter(App.name == name, App.server_id == srv.id).first()
        if existing:
            error(f"App '{name}' already exists on server '{server_name}'")
            raise SystemExit(1)

        if tmpl:
            app_type = f"template:{template_name}"
            effective_port = port or tmpl["port"]
        else:
            app_type = "image" if image else "git" if git_repo else "compose"
            effective_port = port or 3000

        new_app = App(
            name=name,
            server_id=srv.id,
            domain=domain,
            port=effective_port,
            git_repo=git_repo,
            branch=branch,
            image=image,
            app_type=app_type,
            status="stopped",
            replicas=replicas,
        )
        session.add(new_app)

    success(
        f"App '{name}' created on server '{server_name}'. "
        f"Use 'infrakt app deploy {name}' to deploy."
    )


@app.command()
@click.argument("name")
@click.option(
    "--server",
    "server_name",
    default=None,
    help="Server name (optional if app name is unique)",
)
def deploy(name: str, server_name: str | None) -> None:
    """Deploy or redeploy an app."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server

        # Create deployment record
        dep = Deployment(app_id=app_obj.id, status="in_progress")
        session.add(dep)
        session.flush()
        dep_id = dep.id
        app_id = app_obj.id
        app_port = app_obj.port
        app_git = app_obj.git_repo
        app_branch = app_obj.branch
        app_image = app_obj.image
        app_domain = app_obj.domain
        app_cpu_limit = app_obj.cpu_limit
        app_memory_limit = app_obj.memory_limit
        app_replicas = app_obj.replicas
        app_deploy_strategy = app_obj.deploy_strategy
        app_health_check_url = app_obj.health_check_url
        app_health_check_interval = app_obj.health_check_interval
        app_type = app_obj.app_type

        # Check dependencies are running
        dep_names = []
        for d in app_obj.dependencies:
            dep_app = session.query(App).filter(App.id == d.depends_on_app_id).first()
            if dep_app and dep_app.status != "running":
                dep_names.append(dep_app.name)
        if dep_names:
            info(f"Warning: dependencies not running: {', '.join(dep_names)}")

        # Get env content
        env_content = env_content_for_app(app_id)

        ssh = _ssh_for_server(srv)

    try:
        # Generate compose override for template-based apps
        compose_override = None
        if app_type and app_type.startswith("template:"):
            tmpl_name = app_type.split(":", 1)[1]
            compose_override = render_template_compose(tmpl_name, name, app_domain)

        with status_spinner(f"Deploying '{name}'"):
            # Ensure infrakt network exists
            ssh.connect()
            ssh.run("docker network create infrakt 2>/dev/null || true")

            result = deploy_app(
                ssh,
                name,
                git_repo=app_git,
                branch=app_branch,
                image=app_image,
                port=app_port,
                domain=app_domain,
                env_content=env_content,
                compose_override=compose_override,
                cpu_limit=app_cpu_limit,
                memory_limit=app_memory_limit,
                replicas=app_replicas,
                deploy_strategy=app_deploy_strategy,
                health_check_url=app_health_check_url,
                health_check_interval=app_health_check_interval,
            )

            # Set up reverse proxy if domain is configured
            if app_domain:
                # Multi-domain templates (e.g. devtools) need multiple routes
                if app_type and app_type.startswith("template:"):
                    tmpl_name = app_type.split(":", 1)[1]
                    tmpl = get_template(tmpl_name)
                    if tmpl and "domain_map" in tmpl and app_domain and "." in app_domain:
                        # domain_map routes: prefix -> port
                        base = app_domain.split(".", 1)[1]
                        for prefix, svc_port in tmpl["domain_map"].items():
                            svc_domain = f"{prefix}.{base}"
                            add_domain(ssh, svc_domain, svc_port, app_name=f"{name}-{prefix}")
                    else:
                        add_domain(ssh, app_domain, app_port, app_name=name)
                else:
                    add_domain(ssh, app_domain, app_port, app_name=name)

        ssh.close()

        # Update records
        with get_session() as session:
            dep_record = session.query(Deployment).filter(Deployment.id == dep_id).first()
            if dep_record is not None:
                dep_record.status = "success"
                dep_record.log = result.log
                dep_record.commit_hash = result.commit_hash
                dep_record.image_used = result.image_used
                dep_record.finished_at = datetime.utcnow()
            app_record = session.query(App).filter(App.id == app_id).first()
            if app_record is not None:
                app_record.status = "running"

        success(f"App '{name}' deployed successfully")

    except Exception as exc:
        with get_session() as session:
            dep_record = session.query(Deployment).filter(Deployment.id == dep_id).first()
            if dep_record is not None:
                dep_record.status = "failed"
                dep_record.log = str(exc)
                dep_record.finished_at = datetime.utcnow()
            app_record = session.query(App).filter(App.id == app_id).first()
            if app_record is not None:
                app_record.status = "error"
        error(f"Deployment failed: {exc}")
        raise SystemExit(1)


@app.command("list")
@click.option("--server", "server_name", default=None, help="Filter by server")
def list_apps(server_name: str | None) -> None:
    """List all apps."""
    init_db()
    with get_session() as session:
        q = session.query(App).join(Server)
        if server_name:
            q = q.filter(Server.name == server_name)
        apps = q.order_by(Server.name, App.name).all()
        if not apps:
            info("No apps found.")
            return
        rows = [
            (a.name, a.server.name, a.domain or "—", a.port, a.status, a.app_type, a.replicas)
            for a in apps
        ]
    print_table("Apps", ["Name", "Server", "Domain", "Port", "Status", "Type", "Replicas"], rows)


@app.command()
@click.argument("name")
@click.option("--server", "server_name", default=None)
@click.option("--lines", default=100, help="Number of log lines")
@click.option(
    "--deployment", "dep_id", type=int, default=None, help="View historical deployment log"
)
def logs(name: str, server_name: str | None, lines: int, dep_id: int | None) -> None:
    """View app container logs or historical deployment logs."""
    init_db()
    if dep_id is not None:
        with get_session() as session:
            app_obj = _get_app(session, name, server_name)
            dep = (
                session.query(Deployment)
                .filter(Deployment.id == dep_id, Deployment.app_id == app_obj.id)
                .first()
            )
            if not dep or not dep.log:
                error(f"No log found for deployment #{dep_id}")
                raise SystemExit(1)
            console.print(dep.log)
        return

    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server
        ssh = _ssh_for_server(srv)

    with ssh:
        output = get_logs(ssh, name, lines=lines)
    console.print(output)


@app.command()
@click.argument("name")
@click.option("--server", "server_name", default=None)
def restart(name: str, server_name: str | None) -> None:
    """Restart an app's containers."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server
        ssh = _ssh_for_server(srv)

    with status_spinner(f"Restarting '{name}'"):
        with ssh:
            restart_app(ssh, name)

    success(f"App '{name}' restarted")


@app.command()
@click.argument("name")
@click.option("--server", "server_name", default=None)
def stop(name: str, server_name: str | None) -> None:
    """Stop an app's containers."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server
        ssh = _ssh_for_server(srv)
        app_id = app_obj.id

    with status_spinner(f"Stopping '{name}'"):
        with ssh:
            stop_app(ssh, name)

    with get_session() as session:
        a = session.query(App).filter(App.id == app_id).first()
        if a:
            a.status = "stopped"

    success(f"App '{name}' stopped")


@app.command()
@click.argument("name")
@click.option("--server", "server_name", default=None)
@click.option("--force", is_flag=True, help="Skip confirmation")
def destroy(name: str, server_name: str | None, force: bool) -> None:
    """Destroy an app and remove all its data from the server."""
    init_db()
    if not force:
        click.confirm(f"Destroy app '{name}' and all its data?", abort=True)

    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server
        app_domain = app_obj.domain
        ssh = _ssh_for_server(srv)
        app_id = app_obj.id

    with status_spinner(f"Destroying '{name}'"):
        with ssh:
            destroy_app(ssh, name)
            if app_domain:
                remove_domain(ssh, app_domain)

    with get_session() as session:
        app_record = session.query(App).filter(App.id == app_id).first()
        if app_record is not None:
            session.delete(app_record)

    success(f"App '{name}' destroyed")


@app.command()
@click.argument("name")
@click.option("--server", "server_name", default=None)
def health(name: str, server_name: str | None) -> None:
    """Check real container health for an app."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server
        db_status = app_obj.status
        app_id = app_obj.id
        health_url = app_obj.health_check_url
        app_port = app_obj.port
        ssh = _ssh_for_server(srv)

    http_health = None
    with status_spinner(f"Checking health of '{name}'"):
        with ssh:
            containers = get_container_health(ssh, name)
            actual_status = reconcile_app_status(ssh, name)
            if health_url:
                from cli.core.health import check_app_health

                http_health = check_app_health(ssh, app_port, health_url)

    if actual_status != db_status:
        with get_session() as session:
            a = session.query(App).filter(App.id == app_id).first()
            if a:
                a.status = actual_status
        info(f"Status updated: {db_status} → {actual_status}")

    if not containers:
        info(f"No containers found for '{name}' (status: {actual_status})")
        if http_health is not None:
            if http_health["healthy"]:
                success(
                    f"HTTP health ({health_url}): {http_health['status_code']} "
                    f"({http_health['response_time_ms']}ms)"
                )
            else:
                error(
                    f"HTTP health ({health_url}): "
                    f"{http_health.get('status_code', 'N/A')} — "
                    f"{http_health.get('error', 'unhealthy')}"
                )
        return

    rows = [
        (c["name"], c["state"], c["status"], c["health"] or "—", c["image"]) for c in containers
    ]
    print_table(
        f"Health: {name}",
        ["Container", "State", "Status", "Healthcheck", "Image"],
        rows,
    )
    info(f"DB status: {db_status}  |  Actual: {actual_status}")

    if http_health is not None:
        if http_health["healthy"]:
            success(
                f"HTTP health ({health_url}): {http_health['status_code']} "
                f"({http_health['response_time_ms']}ms)"
            )
        else:
            error(
                f"HTTP health ({health_url}): "
                f"{http_health.get('status_code', 'N/A')} — "
                f"{http_health.get('error', 'unhealthy')}"
            )


@app.command()
@click.argument("name")
@click.option("--deployment", "dep_id", type=int, default=None, help="Deployment ID to rollback to")
@click.option("--server", "server_name", default=None)
def rollback(name: str, dep_id: int | None, server_name: str | None) -> None:
    """Roll back an app to a previous successful deployment."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        srv = app_obj.server
        app_id = app_obj.id
        app_port = app_obj.port
        app_git = app_obj.git_repo
        app_branch = app_obj.branch
        app_image = app_obj.image
        app_domain = app_obj.domain

        # Find target deployment
        if dep_id:
            target = (
                session.query(Deployment)
                .filter(
                    Deployment.id == dep_id,
                    Deployment.app_id == app_id,
                    Deployment.status == "success",
                )
                .first()
            )
            if not target:
                error(f"No successful deployment #{dep_id} found for '{name}'")
                raise SystemExit(1)
        else:
            # Default: 2nd most recent success (most recent = current)
            successes = (
                session.query(Deployment)
                .filter(Deployment.app_id == app_id, Deployment.status == "success")
                .order_by(Deployment.started_at.desc())
                .limit(2)
                .all()
            )
            if len(successes) < 2:
                error(f"No previous successful deployment to roll back to for '{name}'")
                raise SystemExit(1)
            target = successes[1]

        pinned_commit = target.commit_hash
        pinned_image = target.image_used
        target_id = target.id

        env_content = env_content_for_app(app_id)
        ssh = _ssh_for_server(srv)

    info(f"Rolling back '{name}' to deployment #{target_id}")

    # Create a new deployment record for the rollback
    with get_session() as session:
        dep = Deployment(app_id=app_id, status="in_progress")
        session.add(dep)
        session.flush()
        new_dep_id = dep.id

    try:
        with status_spinner(f"Rolling back '{name}'"):
            ssh.connect()
            ssh.run("docker network create infrakt 2>/dev/null || true")

            result = deploy_app(
                ssh,
                name,
                git_repo=app_git,
                branch=app_branch,
                image=pinned_image or app_image,
                port=app_port,
                env_content=env_content,
                pinned_commit=pinned_commit,
            )

            if app_domain:
                add_domain(ssh, app_domain, app_port, app_name=name)

        ssh.close()

        with get_session() as session:
            dep_record = session.query(Deployment).filter(Deployment.id == new_dep_id).first()
            if dep_record is not None:
                dep_record.status = "success"
                dep_record.log = result.log
                dep_record.commit_hash = result.commit_hash
                dep_record.image_used = result.image_used
                dep_record.finished_at = datetime.utcnow()
            app_record = session.query(App).filter(App.id == app_id).first()
            if app_record is not None:
                app_record.status = "running"

        success(f"App '{name}' rolled back to deployment #{target_id}")

    except Exception as exc:
        with get_session() as session:
            dep_record = session.query(Deployment).filter(Deployment.id == new_dep_id).first()
            if dep_record is not None:
                dep_record.status = "failed"
                dep_record.log = str(exc)
                dep_record.finished_at = datetime.utcnow()
            app_record = session.query(App).filter(App.id == app_id).first()
            if app_record is not None:
                app_record.status = "error"
        error(f"Rollback failed: {exc}")
        raise SystemExit(1)


@app.command("set-health")
@click.argument("name")
@click.option("--url", "health_url", required=True, help="Health check path (e.g. /health)")
@click.option("--interval", default=60, type=int, help="Check interval in seconds")
@click.option("--server", "server_name", default=None)
def set_health(name: str, health_url: str, interval: int, server_name: str | None) -> None:
    """Configure HTTP health check for an app."""
    init_db()
    if not health_url.startswith("/"):
        error("Health check URL must start with /")
        raise SystemExit(1)
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        app_obj.health_check_url = health_url
        app_obj.health_check_interval = interval
    success(f"Health check configured for '{name}': {health_url} (every {interval}s)")


@app.command("set-limits")
@click.argument("name")
@click.option("--cpu", "cpu_limit", default=None, help="CPU limit (e.g. 1.0, 0.5)")
@click.option("--memory", "memory_limit", default=None, help="Memory limit (e.g. 512m, 1g)")
@click.option("--server", "server_name", default=None)
def set_limits(
    name: str, cpu_limit: str | None, memory_limit: str | None, server_name: str | None
) -> None:
    """Set resource limits for an app."""
    init_db()
    if not cpu_limit and not memory_limit:
        error("Specify at least one of --cpu or --memory")
        raise SystemExit(1)
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        if cpu_limit is not None:
            app_obj.cpu_limit = cpu_limit
        if memory_limit is not None:
            app_obj.memory_limit = memory_limit
    parts = []
    if cpu_limit:
        parts.append(f"CPU: {cpu_limit}")
    if memory_limit:
        parts.append(f"Memory: {memory_limit}")
    success(f"Resource limits for '{name}' updated: {', '.join(parts)}")


@app.command("scale")
@click.argument("name")
@click.option("--replicas", required=True, type=int, help="Number of replicas")
@click.option("--server", "server_name", default=None)
def scale(name: str, replicas: int, server_name: str | None) -> None:
    """Scale an app to N replicas."""
    init_db()
    if replicas < 1:
        error("Replicas must be at least 1")
        raise SystemExit(1)
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        app_obj.replicas = replicas
    success(f"App '{name}' scaled to {replicas} replica(s). Redeploy to apply.")


@app.command("set-strategy")
@click.argument("name")
@click.option(
    "--strategy",
    type=click.Choice(["restart", "rolling"]),
    required=True,
    help="Deploy strategy",
)
@click.option("--server", "server_name", default=None)
def set_strategy(name: str, strategy: str, server_name: str | None) -> None:
    """Set deployment strategy for an app."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        app_obj.deploy_strategy = strategy
    success(f"Deploy strategy for '{name}' set to '{strategy}'")


@app.command("deployments")
@click.argument("name")
@click.option("--server", "server_name", default=None)
@click.option("--limit", default=10, type=int, help="Number of deployments to show")
def list_deployments(name: str, server_name: str | None, limit: int) -> None:
    """List deployment history for an app."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        deps = (
            session.query(Deployment)
            .filter(Deployment.app_id == app_obj.id)
            .order_by(Deployment.started_at.desc())
            .limit(limit)
            .all()
        )
        if not deps:
            info(f"No deployments found for '{name}'")
            return
        rows = [
            (
                d.id,
                d.status,
                d.commit_hash[:8] if d.commit_hash else "—",
                d.image_used or "—",
                str(d.started_at)[:19] if d.started_at else "—",
            )
            for d in deps
        ]
    print_table(
        f"Deployments: {name}",
        ["ID", "Status", "Commit", "Image", "Started"],
        rows,
    )


@app.command("depends")
@click.argument("name")
@click.option("--on", "depends_on", required=True, help="App this depends on")
@click.option("--remove", is_flag=True, help="Remove the dependency")
@click.option("--server", "server_name", default=None)
def depends(name: str, depends_on: str, remove: bool, server_name: str | None) -> None:
    """Manage app dependencies."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        dep_app = session.query(App).filter(App.name == depends_on).first()
        if not dep_app:
            error(f"App '{depends_on}' not found")
            raise SystemExit(1)

        if remove:
            existing = (
                session.query(AppDependency)
                .filter(
                    AppDependency.app_id == app_obj.id,
                    AppDependency.depends_on_app_id == dep_app.id,
                )
                .first()
            )
            if not existing:
                error(f"'{name}' does not depend on '{depends_on}'")
                raise SystemExit(1)
            session.delete(existing)
            success(f"Removed dependency: '{name}' no longer depends on '{depends_on}'")
        else:
            if app_obj.id == dep_app.id:
                error("An app cannot depend on itself")
                raise SystemExit(1)
            # Cycle detection
            if _would_create_cycle(session, app_obj.id, dep_app.id):
                error("Adding this dependency would create a cycle")
                raise SystemExit(1)
            existing = (
                session.query(AppDependency)
                .filter(
                    AppDependency.app_id == app_obj.id,
                    AppDependency.depends_on_app_id == dep_app.id,
                )
                .first()
            )
            if existing:
                info(f"'{name}' already depends on '{depends_on}'")
                return
            session.add(AppDependency(app_id=app_obj.id, depends_on_app_id=dep_app.id))
            success(f"Added dependency: '{name}' depends on '{depends_on}'")


@app.command("deps")
@click.argument("name")
@click.option("--server", "server_name", default=None)
def list_deps(name: str, server_name: str | None) -> None:
    """List dependencies of an app."""
    init_db()
    with get_session() as session:
        app_obj = _get_app(session, name, server_name)
        deps = session.query(AppDependency).filter(AppDependency.app_id == app_obj.id).all()
        if not deps:
            info(f"'{name}' has no dependencies")
            return
        rows = []
        for d in deps:
            dep_app = session.query(App).filter(App.id == d.depends_on_app_id).first()
            if dep_app:
                rows.append((dep_app.name, dep_app.status, dep_app.server.name))
    print_table(f"Dependencies: {name}", ["App", "Status", "Server"], rows)


@app.command("templates")
def list_app_templates() -> None:
    """List available app templates."""
    templates = list_templates()
    if not templates:
        info("No templates available.")
        return
    rows = [
        (t["name"], t["description"], ", ".join(t["services"]), t["port"], t.get("domains", 1))
        for t in templates
    ]
    print_table("App Templates", ["Name", "Description", "Services", "Port", "Domains"], rows)


def _would_create_cycle(session: object, app_id: int, depends_on_id: int) -> bool:
    """Return True if adding app_id -> depends_on_id creates a cycle."""
    visited: set[int] = set()
    stack = [depends_on_id]
    while stack:
        current = stack.pop()
        if current == app_id:
            return True
        if current in visited:
            continue
        visited.add(current)
        deps = (
            session.query(AppDependency)  # type: ignore[attr-defined]
            .filter(AppDependency.app_id == current)
            .all()
        )
        stack.extend(d.depends_on_app_id for d in deps)
    return False
