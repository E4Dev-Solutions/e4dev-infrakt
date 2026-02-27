"""Jinja2-based Docker Compose template renderer."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

TEMPLATES_DIR = Path(__file__).parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(TEMPLATES_DIR)),
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
)


def render_app_compose(
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
    expose_port: bool = True,
) -> str:
    """Render app-compose.yml.j2 with the given parameters."""
    port_var = app_name.upper().replace("-", "_") + "_PORT"
    template = _env.get_template("app-compose.yml.j2")
    return template.render(
        app_name=app_name,
        port=port,
        port_var=port_var,
        image=image,
        build_context=build_context,
        cpu_limit=cpu_limit,
        memory_limit=memory_limit,
        replicas=replicas,
        deploy_strategy=deploy_strategy,
        health_check_url=health_check_url,
        health_check_interval=health_check_interval,
        expose_port=expose_port,
    )


def render_db_compose(
    db_type: str,
    name: str,
    image: str,
    port: int,
    env_vars: dict[str, str],
    volume: str,
) -> str:
    """Render db-compose.yml.j2 with the given parameters."""
    template = _env.get_template("db-compose.yml.j2")
    return template.render(
        db_type=db_type,
        name=name,
        image=image,
        port=port,
        env_vars=env_vars,
        volume=volume,
    )
