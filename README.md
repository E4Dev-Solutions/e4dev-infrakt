# infrakt

A self-hosted PaaS CLI and web dashboard for managing multi-server, multi-app deployments over SSH. infrakt provisions bare Linux VMs into Docker + Caddy hosts, deploys apps via Docker Compose, manages encrypted environment variables, and provisions databases — all from the developer's machine with no remote agent.

## Table of Contents

- [Features](#features)
- [Architecture Overview](#architecture-overview)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [CLI Usage](#cli-usage)
- [Web Dashboard](#web-dashboard)
- [API Usage](#api-usage)
- [Docker Deployment](#docker-deployment)
- [Testing](#testing)
- [Contributing](#contributing)

---

## Features

- **No remote agent.** All operations run over SSH from the local machine using Paramiko. There is no persistent process on the server that could be compromised.
- **Automatic TLS.** Caddy manages HTTPS certificates via Let's Encrypt ACME with zero configuration.
- **Encrypted env vars.** Environment variables are stored locally with Fernet (AES-128-CBC + HMAC-SHA256) encryption and decrypted in memory immediately before being sent to the server over SSH.
- **Multiple deployment modes.** Deploy from a Docker image, a Git repository (with or without a `docker-compose.yml`), or a custom Compose file.
- **Database provisioning.** Create and manage Postgres, MySQL, Redis, and MongoDB services as Docker Compose services, bound to `127.0.0.1` only.
- **Web dashboard.** A React + TypeScript frontend with API key authentication provides browser-based access to all CLI operations.
- **API key auth.** The FastAPI layer requires an `X-API-Key` header on every request. The key is auto-generated at `~/.infrakt/api_key.txt` on first startup.
- **Server hardening.** Provisioning configures UFW (ports 22/80/443 only) and fail2ban (SSH brute-force protection).

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        Developer Machine                         │
│                                                                  │
│  ┌──────────────┐   ┌──────────────────────────────────────┐   │
│  │  infrakt CLI │   │         Web Dashboard                 │   │
│  │  (Click/Python)│  │  React + TanStack Query               │   │
│  └──────┬───────┘   └──────────────┬───────────────────────┘   │
│         │                          │ HTTP /api/* + X-API-Key    │
│         │           ┌──────────────▼───────────────────────┐   │
│         │           │       FastAPI (uvicorn)                │   │
│         │           │       api/main.py + api/routes/        │   │
│         │           └──────────────┬───────────────────────┘   │
│         │                          │                            │
│         └──────────────────────────┘                            │
│                     │  Shared Core (cli/core/, cli/models/)     │
│         ┌───────────┼──────────────────────────┐               │
│         │           │                          │               │
│  ┌──────▼──────┐ ┌──▼──────────┐ ┌────────────▼────┐         │
│  │ provisioner │ │  deployer   │ │  proxy_manager  │         │
│  └─────────────┘ └─────────────┘ └─────────────────┘         │
│                     │ SSHClient (Paramiko)                      │
│                                                                  │
│  ┌──────────────────────────────────────────┐                  │
│  │  Local State (~/.infrakt/)               │                  │
│  │  infrakt.db (SQLite)                     │                  │
│  │  envs/<app_id>.json  (Fernet-encrypted)  │                  │
│  │  master.key (0600)                       │                  │
│  │  api_key.txt (0600)                      │                  │
│  └──────────────────────────────────────────┘                  │
└─────────────────────────────────────────────────────────────────┘
                      │ SSH (port 22)
┌─────────────────────▼───────────────────────────────────────────┐
│                      Remote Server                               │
│                                                                  │
│  /opt/infrakt/                                                   │
│    apps/<app-name>/                                              │
│      docker-compose.yml    (generated or from repo)             │
│      .env                  (decrypted at deploy time)           │
│    caddy/                                                        │
│      Caddyfile             (managed by proxy_manager)           │
│    backups/                                                      │
│                                                                  │
│  Services: Docker, Caddy (auto-HTTPS), UFW, fail2ban            │
└──────────────────────────────────────────────────────────────────┘
```

The CLI and API are architecturally equivalent — they call the same functions in `cli/core/`. The difference is execution context: the CLI runs operations synchronously in the terminal, while the API runs long SSH operations (provisioning, deployment) as FastAPI background tasks and returns immediately.

See [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for a detailed breakdown of every component.

---

## Prerequisites

- **Python 3.11+**
- **Node.js 22+** (for building the frontend; not needed for CLI-only use)
- A remote Linux server accessible via SSH (Ubuntu 22.04+ recommended)
- The remote server must allow SSH login as `root` or a user with `sudo` access

---

## Installation

### Install as a Python package

```bash
git clone https://github.com/your-org/infrakt.git
cd infrakt
pip install -e .
```

This installs the `infrakt` CLI entry point and all Python dependencies.

### Install with development extras

```bash
pip install -e ".[dev]"
```

Adds `pytest`, `pytest-cov`, `mypy`, and `ruff`.

---

## Quick Start

### 1. Initialize

Create the local state directory, generate the encryption master key, and create the SQLite database:

```bash
infrakt init
# Initialized infrakt at /Users/you/.infrakt
```

### 2. Add a server

```bash
infrakt server add \
  --name prod-1 \
  --host 1.2.3.4 \
  --user root \
  --key ~/.ssh/id_ed25519 \
  --provider hetzner
```

infrakt immediately tests the SSH connection and reports whether it succeeded. The server is saved regardless — connectivity issues can be resolved later.

### 3. Provision the server

Installs Docker Engine, Caddy, UFW (ports 22/80/443), and fail2ban. Takes 2–5 minutes on a fresh VM:

```bash
infrakt server provision prod-1
```

### 4. Create a database

```bash
infrakt db create --server prod-1 --name appdb --type postgres
# Connection string: postgresql://appdb:<password>@localhost:5432/appdb
# Save this connection string — the password is not stored locally.
```

### 5. Create and deploy an app

```bash
infrakt app create \
  --server prod-1 \
  --name myapp \
  --git https://github.com/you/myapp.git \
  --domain myapp.example.com \
  --port 3000

infrakt env set myapp \
  DATABASE_URL=postgresql://appdb:<password>@localhost:5432/appdb \
  SECRET_KEY=$(openssl rand -hex 32)

infrakt app deploy myapp
```

The DNS `A` record for `myapp.example.com` must point to the server's IP. Caddy automatically obtains and renews the TLS certificate.

---

## CLI Usage

The CLI provides five command groups. Every subcommand accepts `--help` for option details.

```
infrakt init                      Initialize config and database
infrakt server add                Register a server
infrakt server list               List all servers
infrakt server provision <name>   Install Docker, Caddy, UFW, fail2ban
infrakt server status <name>      Show live CPU/memory/disk/containers
infrakt server ssh <name>         Open an interactive SSH session
infrakt server remove <name>      Remove a server record

infrakt app create                Register a new app (image or git)
infrakt app deploy <name>         Deploy or redeploy an app
infrakt app list                  List all apps
infrakt app logs <name>           Stream container logs
infrakt app restart <name>        Restart without redeploying
infrakt app stop <name>           Stop containers
infrakt app destroy <name>        Stop, delete volumes, remove from server

infrakt env set <app> KEY=VALUE   Encrypt and store env vars
infrakt env get <app> KEY         Print decrypted value
infrakt env list <app>            List keys (values masked by default)
infrakt env delete <app> KEY      Remove a variable from local storage
infrakt env push <app>            Upload .env to server and restart

infrakt db create                 Create a database service
infrakt db list                   List database services
infrakt db destroy <name>         Stop and delete a database service

infrakt proxy add <domain>        Add a Caddy reverse proxy route
infrakt proxy remove <domain>     Remove a proxy route
infrakt proxy domains <server>    List all proxy routes
infrakt proxy status <server>     Show Caddy systemd status
infrakt proxy reload <server>     Graceful Caddy config reload
```

See [`docs/COMMANDS.md`](docs/COMMANDS.md) for the complete reference with all options and examples.

---

## Web Dashboard

The web dashboard provides browser-based access to all infrakt operations. It consists of a FastAPI backend and a React frontend.

### Authentication

The API requires an API key on every request. The key is generated automatically at `~/.infrakt/api_key.txt` the first time the API starts. When you open the dashboard in a browser, you are shown a login screen — paste the key from that file to authenticate.

```bash
cat ~/.infrakt/api_key.txt
```

The key is stored in browser `localStorage` and sent as the `X-API-Key` header on every API request.

### Start in development mode

```bash
# Terminal 1 — start the API
uvicorn api.main:app --reload --port 8000

# Terminal 2 — start the Vite dev server
cd frontend
npm install
npm run dev
```

The frontend starts at `http://localhost:5173` and proxies all `/api/*` requests to `http://localhost:8000`.

### Production build

Build the frontend into `frontend/dist/`. FastAPI detects the directory and serves it automatically:

```bash
cd frontend
npm run build
uvicorn api.main:app --port 8000
```

The full dashboard is available at `http://localhost:8000`.

### Dashboard pages

| Page | Path | Description |
|------|------|-------------|
| Dashboard | `/` | Platform stats: servers, apps, databases, recent deployments |
| Servers | `/servers` | List, add, remove, provision, test connection |
| Server Detail | `/servers/:name` | Live metrics, apps on server, proxy routes |
| Apps | `/apps` | List all apps, create, deploy, stop, destroy |
| App Detail | `/apps/:name` | Logs, deployment history, environment variables |
| Databases | `/databases` | List database services, create, destroy |

---

## API Usage

The API is available at `http://localhost:8000/api`. Every request must include the `X-API-Key` header.

```bash
API_KEY=$(cat ~/.infrakt/api_key.txt)

# List servers
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/servers

# Deploy an app
curl -X POST -H "X-API-Key: $API_KEY" http://localhost:8000/api/apps/myapp/deploy

# Get dashboard stats
curl -H "X-API-Key: $API_KEY" http://localhost:8000/api/dashboard
```

Interactive documentation is available at `http://localhost:8000/docs` (Swagger UI) when the server is running. The Swagger UI includes an "Authorize" button where you can enter the API key to authenticate all requests in the browser.

See [`docs/API.md`](docs/API.md) for the complete endpoint reference.

---

## Docker Deployment

infrakt ships a multi-stage Dockerfile and a `docker-compose.yml` for running the dashboard as a long-lived service.

### Build and run

```bash
docker compose up -d
```

The compose file mounts `~/.infrakt` and `~/.ssh` from the host so the container shares state with any local `infrakt` CLI usage and can authenticate SSH connections using your existing keys.

```yaml
volumes:
  - "${HOME}/.infrakt:/home/infrakt/.infrakt"
  - "${HOME}/.ssh:/home/infrakt/.ssh:ro"
```

**Important:** The SSH key mount is read-only. The `.infrakt` mount is read-write so the container can generate the master encryption key and API key on first startup.

### Access

After starting the container, open `http://localhost:8000` in a browser. Retrieve the API key:

```bash
cat ~/.infrakt/api_key.txt
```

### Docker image details

The Dockerfile uses two stages:

1. **`frontend-build`** (Node 22 Alpine) — compiles the React/TypeScript dashboard into `frontend/dist/`
2. **`runtime`** (Python 3.13 slim) — runs FastAPI/uvicorn with the pre-built frontend copied in

The runtime image runs as a non-root user (`infrakt`) and has a health check that hits `http://localhost:8000/docs` every 30 seconds.

---

## Testing

### Run the test suite

```bash
pytest -v
```

### Run with coverage

```bash
pytest --cov=cli --cov-report=term-missing -v
```

Tests use an `isolated_config` fixture (defined in `tests/conftest.py`) that redirects all state to a temporary directory, so tests never touch `~/.infrakt`. SSH operations are mocked via a `mock_ssh` fixture.

### Lint and format

```bash
ruff check .           # check for lint errors
ruff format --check .  # check formatting without modifying files
ruff format .          # apply formatting
```

### Type check

```bash
mypy cli/ --ignore-missing-imports
```

### Frontend

```bash
cd frontend
npm run type-check   # TypeScript type check (tsc -b --noEmit)
npm run build        # production build (also validates types)
```

### CI

GitHub Actions runs five jobs on every push and PR to `main`:

| Job | What it runs |
|-----|-------------|
| `lint` | `ruff check` + `ruff format --check` |
| `test` | `pytest --cov=cli` |
| `typecheck` | `mypy cli/ --ignore-missing-imports` |
| `frontend-build` | `npm ci && npm run build` |
| `docker-build` | Multi-stage Docker build (no push) |

All five must pass before merging.

---

## Contributing

### Development setup

```bash
git clone https://github.com/your-org/infrakt.git
cd infrakt
pip install -e ".[dev]"
```

### Project structure

```
cli/
  main.py              # Click entry point, registers all command groups
  commands/            # CLI command groups (server, app, env, db, proxy)
  core/                # Shared business logic (used by both CLI and API)
    config.py          # Path constants: INFRAKT_HOME, DB_PATH, ENVS_DIR, etc.
    database.py        # SQLAlchemy engine, session factory, init_db()
    ssh.py             # SSHClient wrapper (Paramiko)
    provisioner.py     # Server provisioning steps
    deployer.py        # Docker Compose deployment engine
    proxy_manager.py   # Caddy Caddyfile management via SSH
    crypto.py          # Fernet encrypt/decrypt for env vars
    console.py         # Rich-based output helpers
    exceptions.py      # Custom exception hierarchy
  models/              # SQLAlchemy ORM models (Server, App, Deployment)
  templates/           # Jinja2 templates (reserved for future use)

api/
  main.py              # FastAPI app, CORS config, router registration
  auth.py              # API key generation and validation
  schemas.py           # Pydantic request/response models (with input validation)
  routes/              # One module per resource (dashboard, servers, apps, env,
                       # databases, proxy)

frontend/
  src/
    api/client.ts      # Typed fetch wrappers for all API endpoints
    hooks/useApi.ts    # TanStack Query hooks
    pages/             # React page components
    components/        # Shared UI components

tests/
  conftest.py          # isolated_config and mock_ssh fixtures
  unit/                # Unit tests for core modules
  integration/         # Integration tests
```

### Code style

- Python: `ruff` for linting and formatting, `mypy --strict` for type checking
- TypeScript: `tsc -b` for type checking, `vite build` for the production bundle
- Line length: 100 characters (Python), default Prettier settings (TypeScript via Vite)
- All new code must pass lint, type check, and tests before merging

### Security notes for contributors

- **Input validation:** All API request bodies are validated by Pydantic schemas in `api/schemas.py`. Shell injection is prevented via `shlex.quote()` in `cli/core/deployer.py` and SSRF is blocked by the `git_repo` validator in `AppCreate`.
- **No secret storage:** The database password printed by `infrakt db create` is intentionally not stored. Do not add storage for it.
- **Master key:** `~/.infrakt/master.key` must never be logged or included in error messages.
- **API key:** `~/.infrakt/api_key.txt` is compared with `hmac.compare_digest` to prevent timing attacks.
