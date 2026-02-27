"""Built-in app templates for one-click deployment.

Each template defines a complete Docker Compose stack that can be deployed
with a single command. Templates follow the same pattern as DB_TEMPLATES
in cli/commands/db.py — a static registry keyed by template name.
"""

from __future__ import annotations

import secrets
from typing import TypedDict


class TemplateInfo(TypedDict, total=False):
    name: str
    description: str
    services: list[str]
    port: int
    domains: int
    domain_map: dict[str, int]  # extra domains: prefix -> port


def _secret() -> str:
    return secrets.token_urlsafe(24)


def _nginx_compose(name: str, domain: str | None) -> str:
    return f"""\
services:
  {name}:
    image: nginx:alpine
    container_name: infrakt-{name}
    restart: unless-stopped
    env_file:
      - .env
    expose:
      - "80"
    networks:
      - infrakt

networks:
  infrakt:
    name: infrakt
    external: true
"""


def _uptime_kuma_compose(name: str, domain: str | None) -> str:
    return f"""\
services:
  {name}:
    image: louislam/uptime-kuma:1
    container_name: infrakt-{name}
    restart: unless-stopped
    env_file:
      - .env
    expose:
      - "3001"
    volumes:
      - {name}-data:/app/data
    networks:
      - infrakt

volumes:
  {name}-data:

networks:
  infrakt:
    name: infrakt
    external: true
"""


def _n8n_compose(name: str, domain: str | None) -> str:
    db_pass = _secret()
    url = f"https://{domain}/" if domain else "http://localhost:5678/"
    host = domain or "localhost"
    return f"""\
services:
  {name}:
    image: n8nio/n8n:latest
    container_name: infrakt-{name}
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - DB_TYPE=postgresdb
      - DB_POSTGRESDB_HOST={name}-db
      - DB_POSTGRESDB_PORT=5432
      - DB_POSTGRESDB_DATABASE=n8n
      - DB_POSTGRESDB_USER=n8n
      - DB_POSTGRESDB_PASSWORD={db_pass}
      - N8N_HOST={host}
      - N8N_PROTOCOL=https
      - WEBHOOK_URL={url}
    expose:
      - "5678"
    volumes:
      - {name}-data:/home/node/.n8n
    networks:
      - infrakt
    depends_on:
      {name}-db:
        condition: service_healthy

  {name}-db:
    image: postgres:16-alpine
    container_name: infrakt-{name}-db
    restart: unless-stopped
    environment:
      - POSTGRES_DB=n8n
      - POSTGRES_USER=n8n
      - POSTGRES_PASSWORD={db_pass}
    volumes:
      - {name}-pgdata:/var/lib/postgresql/data
    networks:
      - infrakt
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U n8n"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  {name}-data:
  {name}-pgdata:

networks:
  infrakt:
    name: infrakt
    external: true
"""


def _docmost_compose(name: str, domain: str | None) -> str:
    db_pass = _secret()
    app_secret = _secret()
    url = f"https://{domain}" if domain else "http://localhost:3000"
    return f"""\
services:
  {name}:
    image: docmost/docmost:latest
    container_name: infrakt-{name}
    restart: unless-stopped
    env_file:
      - .env
    environment:
      - APP_URL={url}
      - APP_SECRET={app_secret}
      - DATABASE_URL=postgresql://docmost:{db_pass}@{name}-db:5432/docmost?sslmode=disable
      - REDIS_URL=redis://{name}-redis:6379
    expose:
      - "3000"
    networks:
      - infrakt
    depends_on:
      {name}-db:
        condition: service_healthy
      {name}-redis:
        condition: service_healthy

  {name}-db:
    image: postgres:16-alpine
    container_name: infrakt-{name}-db
    restart: unless-stopped
    environment:
      - POSTGRES_DB=docmost
      - POSTGRES_USER=docmost
      - POSTGRES_PASSWORD={db_pass}
    volumes:
      - {name}-pgdata:/var/lib/postgresql/data
    networks:
      - infrakt
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U docmost"]
      interval: 10s
      timeout: 5s
      retries: 5

  {name}-redis:
    image: redis:7-alpine
    container_name: infrakt-{name}-redis
    restart: unless-stopped
    volumes:
      - {name}-redis-data:/data
    networks:
      - infrakt
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  {name}-pgdata:
  {name}-redis-data:

networks:
  infrakt:
    name: infrakt
    external: true
"""


def _devtools_compose(name: str, domain: str | None) -> str:
    db_pass = _secret()
    # domain may be a JSON dict for multi-domain templates
    git_domain = domain
    if domain and domain.startswith("{"):
        import json
        try:
            domains = json.loads(domain)
            git_domain = domains.get("gitea", domain)
        except json.JSONDecodeError:
            git_domain = domain
    return f"""\
services:
  {name}-gitea:
    image: gitea/gitea:latest
    container_name: infrakt-{name}-gitea
    restart: unless-stopped
    environment:
      - GITEA__database__DB_TYPE=postgres
      - GITEA__database__HOST={name}-db:5432
      - GITEA__database__NAME=gitea
      - GITEA__database__USER=gitea
      - GITEA__database__PASSWD={db_pass}
      - GITEA__server__ROOT_URL=https://{git_domain}/
      - GITEA__server__DOMAIN={git_domain}
      - GITEA__server__SSH_DOMAIN={git_domain}
      - GITEA__server__HTTP_PORT=3000
    expose:
      - "3000"
    volumes:
      - {name}-gitea-data:/data
    networks:
      - infrakt
    depends_on:
      {name}-db:
        condition: service_healthy

  {name}-portainer:
    image: portainer/portainer-ce:lts
    container_name: infrakt-{name}-portainer
    restart: unless-stopped
    expose:
      - "9000"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - {name}-portainer-data:/data
    networks:
      - infrakt

  {name}-db:
    image: postgres:16-alpine
    container_name: infrakt-{name}-db
    restart: unless-stopped
    environment:
      - POSTGRES_DB=gitea
      - POSTGRES_USER=gitea
      - POSTGRES_PASSWORD={db_pass}
    volumes:
      - {name}-pgdata:/var/lib/postgresql/data
    networks:
      - infrakt
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U gitea"]
      interval: 10s
      timeout: 5s
      retries: 5

volumes:
  {name}-gitea-data:
  {name}-portainer-data:
  {name}-pgdata:

networks:
  infrakt:
    name: infrakt
    external: true
"""


# ── Template Registry ──────────────────────────────────────────

APP_TEMPLATES: dict[str, TemplateInfo] = {
    "nginx": {
        "name": "nginx",
        "description": "Static site with nginx",
        "services": ["nginx"],
        "port": 80,
        "domains": 1,
    },
    "uptime-kuma": {
        "name": "uptime-kuma",
        "description": "Uptime monitoring dashboard",
        "services": ["uptime-kuma"],
        "port": 3001,
        "domains": 1,
    },
    "n8n": {
        "name": "n8n",
        "description": "Workflow automation with Postgres",
        "services": ["n8n", "postgres"],
        "port": 5678,
        "domains": 1,
    },
    "docmost": {
        "name": "docmost",
        "description": "Collaborative wiki with Postgres and Redis",
        "services": ["docmost", "postgres", "redis"],
        "port": 3000,
        "domains": 1,
    },
    "devtools": {
        "name": "devtools",
        "description": "Gitea + Portainer with Postgres",
        "services": ["gitea", "portainer", "postgres"],
        "port": 3000,
        "domains": 2,
        "domain_map": {"gitea": 3000, "portainer": 9000},
    },
}

# Map template name → compose generator function
_COMPOSE_GENERATORS: dict[str, callable] = {
    "nginx": _nginx_compose,
    "uptime-kuma": _uptime_kuma_compose,
    "n8n": _n8n_compose,
    "docmost": _docmost_compose,
    "devtools": _devtools_compose,
}


def get_template(name: str) -> TemplateInfo | None:
    """Look up a template by name."""
    return APP_TEMPLATES.get(name)


def list_templates() -> list[TemplateInfo]:
    """Return all available templates."""
    return list(APP_TEMPLATES.values())


def render_template_compose(
    template_name: str, app_name: str, domain: str | None = None
) -> str:
    """Render the docker-compose.yml for a template.

    Raises KeyError if template_name is not found.
    """
    gen = _COMPOSE_GENERATORS.get(template_name)
    if gen is None:
        raise KeyError(f"Unknown template: {template_name}")
    return gen(app_name, domain)
