# infrakt

A self-hosted PaaS CLI and web dashboard for managing multi-server, multi-app deployments over SSH. infrakt provisions bare VMs into Docker + Caddy hosts, deploys apps via Docker Compose, manages encrypted environment variables, and provisions databases — all without any remote agent.

## Table of Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [CLI Command Reference](#cli-command-reference)
- [Web Dashboard](#web-dashboard)
- [Development Setup](#development-setup)
- [Security Model](#security-model)
- [Tech Stack](#tech-stack)

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Developer Machine                         │
│                                                                  │
│  ┌──────────────┐   ┌──────────────────────────────────────┐   │
│  │  infrakt CLI │   │         Web Dashboard                 │   │
│  │  (Click/Python)│  │  React + TanStack Query               │   │
│  └──────┬───────┘   └──────────────┬───────────────────────┘   │
│         │                          │ HTTP /api/*                │
│         │           ┌──────────────▼───────────────────────┐   │
│         │           │       FastAPI (uvicorn)                │   │
│         │           │       api/main.py + api/routes/        │   │
│         │           └──────────────┬───────────────────────┘   │
│         │                          │                            │
│         └──────────────────────────┘                            │
│                     │  Core Modules                             │
│         ┌───────────┼──────────────────────────┐               │
│         │           │                          │               │
│  ┌──────▼──────┐ ┌──▼──────────┐ ┌────────────▼────┐         │
│  │ provisioner │ │  deployer   │ │  proxy_manager  │         │
│  └─────────────┘ └─────────────┘ └─────────────────┘         │
│         │           │                          │               │
│         └───────────┴──────────────────────────┘               │
│                     │ SSHClient (Paramiko)                      │
│                     │                                           │
│  ┌──────────────────────────────────────────┐                  │
│  │  Local State (~/.infrakt/)               │                  │
│  │  infrakt.db (SQLite)                     │                  │
│  │  envs/<app_id>.json  (Fernet-encrypted)  │                  │
│  │  master.key (0600)                       │                  │
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

### Project Layout

```
cli/
  main.py              # Click entry point, registers all command groups
  commands/            # CLI command groups
    server.py          # infrakt server *
    app.py             # infrakt app *
    env.py             # infrakt env *
    db.py              # infrakt db *
    proxy.py           # infrakt proxy *
  core/                # Business logic (shared by CLI and API)
    config.py          # Paths: INFRAKT_HOME, DB_PATH, ENVS_DIR, etc.
    database.py        # SQLAlchemy engine, session factory, init_db()
    ssh.py             # SSHClient wrapper (Paramiko)
    provisioner.py     # Server provisioning steps (Docker, Caddy, UFW, fail2ban)
    deployer.py        # Docker Compose deployment engine
    proxy_manager.py   # Caddy Caddyfile read/write/reload via SSH
    crypto.py          # Fernet encrypt/decrypt for env vars
    console.py         # Rich-based output helpers
    exceptions.py      # Custom exception hierarchy
  models/              # SQLAlchemy ORM models
    server.py          # Server model
    app.py             # App model (also used for database services)
    deployment.py      # Deployment model
  templates/           # Jinja2 templates (reserved for future use)

api/
  main.py              # FastAPI app, CORS config, router registration (all routes require API key)
  auth.py              # API key generation (secrets.token_urlsafe), validation (hmac.compare_digest)
  schemas.py           # Pydantic request/response models (includes name/domain/SSRF validation)
  routes/
    dashboard.py       # GET /api/dashboard
    servers.py         # /api/servers/*
    apps.py            # /api/apps/*
    env.py             # /api/apps/{name}/env/*
    databases.py       # /api/databases/*
    proxy.py           # /api/proxy/*

frontend/
  src/
    api/client.ts      # Typed fetch wrappers; stores/sends API key via X-API-Key header
    hooks/useApi.ts    # TanStack Query hooks (useServers, useApps, etc.)
    pages/             # Login, Dashboard, Servers, ServerDetail, Apps, AppDetail, Databases
    components/        # Layout (with logout), StatusBadge, DataTable, Modal, Toast, EmptyState

tests/
  conftest.py          # isolated_config fixture (temp dir), mock_ssh fixture
  unit/                # Unit tests for core modules
  integration/         # Integration tests
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- A remote Linux server accessible via SSH (Ubuntu 22.04+ recommended)
- The server must allow SSH login as root or a sudo user

### Install

```bash
pip install -e .
```

### Initialize

Create the local config directory (`~/.infrakt/`), generate the master encryption key, and create the SQLite database:

```bash
infrakt init
# Initialized infrakt at /Users/you/.infrakt
```

### Add a Server

```bash
infrakt server add \
  --name prod-1 \
  --host 1.2.3.4 \
  --user root \
  --key ~/.ssh/id_ed25519 \
  --provider hetzner
```

infrakt immediately tests the SSH connection and reports whether it succeeded.

### Provision the Server

Installs Docker, Caddy, UFW (ports 22/80/443), and fail2ban. This takes 2–5 minutes:

```bash
infrakt server provision prod-1
```

### Create and Deploy an App

**From a Docker image:**

```bash
infrakt app create \
  --server prod-1 \
  --name myapp \
  --image nginx:alpine \
  --domain myapp.example.com \
  --port 80

infrakt app deploy myapp
```

**From a Git repository:**

```bash
infrakt app create \
  --server prod-1 \
  --name api \
  --git https://github.com/you/api.git \
  --branch main \
  --domain api.example.com \
  --port 3000

infrakt app deploy api
```

If your repository contains a `docker-compose.yml`, infrakt uses it directly. Otherwise it generates a minimal one.

### Set Environment Variables

```bash
infrakt env set myapp DATABASE_URL=postgres://... SECRET_KEY=abc123

# Redeploy to apply changes, or push directly:
infrakt env push myapp
```

### Create a Database

```bash
infrakt db create \
  --server prod-1 \
  --name mydb \
  --type postgres

# Outputs: postgresql://mydb:<password>@localhost:5432/mydb
# Save the connection string — the password is not stored locally.
```

---

## CLI Command Reference

### `infrakt init`

Initialize the local config directory and database. Safe to run multiple times.

```bash
infrakt init
```

Creates: `~/.infrakt/`, `~/.infrakt/infrakt.db`, `~/.infrakt/envs/`, `~/.infrakt/keys/`, `~/.infrakt/master.key` (0600).

---

### `infrakt server`

Manage remote servers.

#### `infrakt server add`

Register a new server and test SSH connectivity.

```bash
infrakt server add [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--name` | text | prompted | Unique name for the server |
| `--host` | text | prompted | IP address or hostname |
| `--user` | text | `root` | SSH username |
| `--port` | int | `22` | SSH port |
| `--key` | path | none | Path to SSH private key file |
| `--provider` | text | none | Cloud provider label (e.g. `hetzner`, `digitalocean`) |

```bash
infrakt server add --name prod-1 --host 1.2.3.4 --key ~/.ssh/id_ed25519
```

#### `infrakt server list`

List all registered servers with their status, host, and app count.

```bash
infrakt server list
```

#### `infrakt server remove <name>`

Remove a registered server from the local database. Prompts for confirmation if the server has apps registered.

```bash
infrakt server remove prod-1
infrakt server remove prod-1 --force   # skip confirmation
```

| Option | Description |
|--------|-------------|
| `--force` | Skip confirmation prompt |

#### `infrakt server provision <name>`

Provision a server via SSH. Installs: Docker Engine, Caddy (with auto-HTTPS), UFW (deny inbound except 22/80/443), fail2ban, and creates `/opt/infrakt/{apps,caddy,backups}/`.

```bash
infrakt server provision prod-1
```

Sets server status to `active` on completion.

#### `infrakt server status <name>`

Show live system metrics from the server: uptime, memory usage, disk usage, and running Docker containers.

```bash
infrakt server status prod-1
```

#### `infrakt server ssh <name>`

Open an interactive SSH session to the server using the registered credentials.

```bash
infrakt server ssh prod-1
```

---

### `infrakt app`

Manage application deployments.

#### `infrakt app create`

Register a new app on a server. Does not deploy — use `infrakt app deploy` after creating.

```bash
infrakt app create [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--server` | text | required | Target server name |
| `--name` | text | required | App name (unique per server) |
| `--domain` | text | none | Domain for reverse proxy (e.g. `app.example.com`) |
| `--port` | int | `3000` | Container port the app listens on |
| `--git` | url | none | Git repository URL |
| `--branch` | text | `main` | Git branch to deploy |
| `--image` | text | none | Docker image (e.g. `nginx:alpine`) |

The app type is inferred: `image` if `--image` is set, `git` if `--git` is set, otherwise `compose`.

```bash
# Image-based
infrakt app create --server prod-1 --name web --image nginx:alpine --port 80

# Git-based
infrakt app create --server prod-1 --name api --git https://github.com/you/api --port 3000
```

#### `infrakt app deploy <name>`

Deploy or redeploy an app. Pulls/clones source, uploads environment variables, runs `docker compose up -d`, and configures the Caddy reverse proxy if a domain is set.

```bash
infrakt app deploy myapp
infrakt app deploy myapp --server prod-1   # disambiguate if name is not unique
```

| Option | Description |
|--------|-------------|
| `--server` | Filter by server name (optional if app name is unique) |

#### `infrakt app list`

List all apps across all servers.

```bash
infrakt app list
infrakt app list --server prod-1   # filter by server
```

#### `infrakt app logs <name>`

Stream container logs from the remote server.

```bash
infrakt app logs myapp
infrakt app logs myapp --lines 200
```

| Option | Default | Description |
|--------|---------|-------------|
| `--lines` | `100` | Number of log lines to retrieve |
| `--server` | none | Filter by server |

#### `infrakt app restart <name>`

Restart the app's Docker Compose services without redeploying.

```bash
infrakt app restart myapp
```

#### `infrakt app stop <name>`

Stop the app's containers. Sets status to `stopped` in the database.

```bash
infrakt app stop myapp
```

#### `infrakt app destroy <name>`

Stop containers, remove all volumes, and delete `/opt/infrakt/apps/<name>/` from the server. Also removes the Caddy proxy route if a domain was configured. Removes the app record from the local database.

```bash
infrakt app destroy myapp
infrakt app destroy myapp --force   # skip confirmation
```

---

### `infrakt env`

Manage app environment variables. Variables are stored encrypted at rest in `~/.infrakt/envs/<app_id>.json` using Fernet symmetric encryption.

#### `infrakt env set <app_name> <KEY=VALUE> ...`

Set one or more environment variables. Values are encrypted before being written to disk.

```bash
infrakt env set myapp DATABASE_URL=postgres://... SECRET_KEY=abc123 DEBUG=false
```

After setting variables, either run `infrakt app deploy myapp` or `infrakt env push myapp` to apply them to the running container.

#### `infrakt env get <app_name> <KEY>`

Print the decrypted value of a single variable.

```bash
infrakt env get myapp DATABASE_URL
```

#### `infrakt env list <app_name>`

List all environment variable keys for an app. Values are masked by default.

```bash
infrakt env list myapp
infrakt env list myapp --show-values   # decrypt and display values
```

| Option | Description |
|--------|-------------|
| `--show-values` | Display decrypted plaintext values |

#### `infrakt env delete <app_name> <KEY>`

Delete an environment variable from local storage.

```bash
infrakt env delete myapp OLD_SECRET
```

#### `infrakt env push <app_name>`

Write all decrypted environment variables to `/opt/infrakt/apps/<name>/.env` on the server, then restart the containers.

```bash
infrakt env push myapp
```

---

### `infrakt db`

Manage database services on servers. Databases run as Docker Compose services in the `infrakt` network and are bound to `127.0.0.1` only (not exposed to the internet).

Supported types: `postgres`, `mysql`, `redis`, `mongo`

Default versions: Postgres 16, MySQL 8, Redis 7-alpine, MongoDB 7

#### `infrakt db create`

Create and start a database service. Generates a cryptographically random password. Prints the connection string once — it is not stored locally.

```bash
infrakt db create --server prod-1 --name mydb --type postgres
infrakt db create --server prod-1 --name cache --type redis
infrakt db create --server prod-1 --name mydb --type postgres --version 15
```

| Option | Required | Default | Description |
|--------|----------|---------|-------------|
| `--server` | yes | — | Target server name |
| `--name` | yes | — | Database service name |
| `--type` | yes | — | One of: `postgres`, `mysql`, `redis`, `mongo` |
| `--version` | no | latest stable | Image version tag |

#### `infrakt db destroy <name>`

Stop the database, remove all data volumes, and delete the app directory.

```bash
infrakt db destroy mydb --server prod-1
infrakt db destroy mydb --server prod-1 --force
```

**Warning:** This deletes all database data permanently.

#### `infrakt db list`

List all database services.

```bash
infrakt db list
infrakt db list --server prod-1
```

---

### `infrakt proxy`

Manage the Caddy reverse proxy configuration. Caddy is configured automatically during `infrakt server provision`. The Caddyfile is stored at `/opt/infrakt/caddy/Caddyfile` on the server and managed entirely via SSH — Caddy handles TLS certificates automatically via ACME.

#### `infrakt proxy setup <server_name>`

Initialize Caddy on a server. This runs automatically during provisioning; only use manually if re-configuring.

```bash
infrakt proxy setup prod-1
```

#### `infrakt proxy add <domain>`

Add a reverse proxy route from a domain to a local port.

```bash
infrakt proxy add api.example.com --server prod-1 --port 3000
```

| Option | Required | Description |
|--------|----------|-------------|
| `--server` | yes | Server name |
| `--port` | yes | Local port to forward to |

#### `infrakt proxy remove <domain>`

Remove a proxy route and reload Caddy.

```bash
infrakt proxy remove api.example.com --server prod-1
```

#### `infrakt proxy domains <server_name>`

List all active proxy routes on a server.

```bash
infrakt proxy domains prod-1
```

#### `infrakt proxy status <server_name>`

Show the systemd status of the Caddy service.

```bash
infrakt proxy status prod-1
```

#### `infrakt proxy reload <server_name>`

Reload the Caddy configuration without restarting (graceful reload).

```bash
infrakt proxy reload prod-1
```

---

## Web Dashboard

The web dashboard provides a browser UI for the same operations available in the CLI. It consists of a FastAPI backend and a React frontend.

### Authentication

Every API route requires an `X-API-Key` header. The key is auto-generated at `~/.infrakt/api_key.txt` on the first API startup. The React app shows a login page on first visit — paste the key from that file to authenticate. The key is stored in browser `localStorage` and attached to every subsequent request.

```bash
# Retrieve the API key
cat ~/.infrakt/api_key.txt
```

### Start the API

```bash
uvicorn api.main:app --reload --port 8000
```

The API auto-initializes the database on startup and serves at `http://localhost:8000`. Interactive API docs (with API key authentication support) are available at `http://localhost:8000/docs`.

### Start the Frontend (Development)

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server starts at `http://localhost:5173` and proxies all `/api/*` requests to `http://localhost:8000`.

### Production Build

Build the frontend into `frontend/dist/`. The FastAPI app will serve it automatically:

```bash
cd frontend
npm run build
```

Then start the API only:

```bash
uvicorn api.main:app --port 8000
```

The full dashboard is now available at `http://localhost:8000`.

### Dashboard Pages

| Page | Route | Description |
|------|-------|-------------|
| Login | (no route, shown before auth) | API key entry; validates key against `GET /api/dashboard` |
| Dashboard | `/` | Platform stats: servers, apps, databases, recent deployments |
| Servers | `/servers` | List servers, add/remove, provision, test connection |
| Server Detail | `/servers/:name` | Live metrics, app list, proxy routes |
| Apps | `/apps` | List all apps, create, deploy, stop, destroy |
| App Detail | `/apps/:name` | Logs, deployment history, environment variables |
| Databases | `/databases` | List database services, create, destroy |

---

## Development Setup

### Install Dependencies

```bash
pip install -e ".[dev]"
```

This installs the package in editable mode plus the dev extras: `pytest`, `pytest-cov`, `mypy`, and `ruff`.

### Run Tests

```bash
pytest -v
pytest --cov=cli --cov-report=term-missing -v   # with coverage
```

Tests use an isolated config fixture that redirects all state (`~/.infrakt/`) to a temporary directory. SSH calls are mocked via a `mock_ssh` fixture in `tests/conftest.py`.

### Lint and Format

```bash
ruff check .           # check for lint errors
ruff format --check .  # check formatting
ruff format .          # apply formatting
```

### Type Check

```bash
mypy cli/ --ignore-missing-imports
```

### CI

GitHub Actions runs five jobs on every push and PR to `main`:
- **lint**: `ruff check` + `ruff format --check`
- **test**: `pytest --cov=cli`
- **typecheck**: `mypy cli/ --ignore-missing-imports`
- **frontend-build**: `npm ci && npm run build` (validates TypeScript types and the Vite production build)
- **docker-build**: multi-stage Docker image build (`docker/build-push-action`, no push)

All five must pass before merging. The `docker-build` job depends on `frontend-build` so the Node build is validated before the Docker layer cache is used.

### Frontend Development

```bash
cd frontend
npm install
npm run dev          # start Vite dev server at :5173
npm run type-check   # TypeScript type check
npm run build        # production build to frontend/dist/
```

---

## Security Model

**No remote agent.** infrakt runs entirely from the developer's machine over SSH. There is no persistent daemon on the server that could be compromised.

**SSH-only access.** All remote operations (provisioning, deploying, log retrieval, proxy management) go through a Paramiko SSH connection using either key-based or agent authentication. Password authentication is not used by infrakt.

**Encrypted environment variables.** Env vars are stored locally in `~/.infrakt/envs/<app_id>.json`. Each value is encrypted with Fernet (AES-128-CBC + HMAC-SHA256) using a master key stored in `~/.infrakt/master.key` with permissions `0600`. The plaintext is only decrypted immediately before being sent to the server at deploy time, and then only over the encrypted SSH channel.

**API key authentication.** The FastAPI layer requires an `X-API-Key` header on every request. The key is generated with `secrets.token_urlsafe(32)` (256 bits of entropy) and stored at `~/.infrakt/api_key.txt` (chmod `0600`). Keys are compared with `hmac.compare_digest` to prevent timing attacks. Missing key: `401`. Wrong key: `403`.

**Shell injection prevention.** All user-controlled values passed to remote shell commands are sanitized with `shlex.quote()` in `cli/core/deployer.py`. App names, branch names, and image references are validated against strict allowlist regular expressions before use in any shell command.

**SSRF prevention.** The `git_repo` field in `AppCreate` (Pydantic schema) validates that the URL uses HTTPS, ends in `.git`, and does not resolve to localhost, RFC-1918 ranges (`10.x`, `172.16-31.x`, `192.168.x`), or link-local addresses.

**Server hardening.** The provisioning step configures:
- UFW firewall: deny all inbound except SSH (22), HTTP (80), HTTPS (443)
- fail2ban: blocks brute-force SSH attempts
- All database ports are bound to `127.0.0.1` only — never exposed publicly

**Automatic TLS.** Caddy obtains and renews TLS certificates automatically via ACME (Let's Encrypt). Apps served over a custom domain always get HTTPS with zero configuration.

**Database passwords.** When `infrakt db create` generates a database, it uses `secrets.token_urlsafe(24)` for the password, which provides 144 bits of entropy. The password is not stored by infrakt — it is printed once and must be saved externally (e.g. in an app's env vars via `infrakt env set`).

---

## Tech Stack

### CLI and API (Python)

| Component | Library | Version |
|-----------|---------|---------|
| CLI framework | Click | >=8.1 |
| Terminal output | Rich | >=13.0 |
| SSH client | Paramiko | >=3.4 |
| Database ORM | SQLAlchemy 2.0 | >=2.0 |
| Database engine | SQLite | (stdlib) |
| Template engine | Jinja2 | >=3.1 |
| Encryption | cryptography (Fernet) | >=42.0 |
| API framework | FastAPI | >=0.115 |
| ASGI server | Uvicorn | >=0.34 |

### Frontend (TypeScript)

| Component | Library | Version |
|-----------|---------|---------|
| UI framework | React | ^19.0.0 |
| Routing | React Router | ^7.1.1 |
| Data fetching | TanStack Query | ^5.62.7 |
| Styling | Tailwind CSS | ^4.0.0 |
| Icons | Lucide React | ^0.468.0 |
| Build tool | Vite | ^6.0.5 |

### Key Design Decisions

- **No remote agent** — everything is SSH-based, eliminating a persistent attack surface on the server
- **Caddy for auto-HTTPS** — zero TLS configuration, automatic certificate renewal
- **Docker Compose for app orchestration** — portable, no Kubernetes complexity
- **SQLite for local state** — portable, zero-dependency, single-file backup
- **Env vars encrypted at rest** — Fernet encryption with a local master key (never stored remotely)
- **Databases stored as App records** — the `App` model is reused with `app_type = "db:<type>"`, keeping the schema simple
- **Shared core modules** — CLI and API both import from `cli/core/`, ensuring identical behavior through both interfaces
