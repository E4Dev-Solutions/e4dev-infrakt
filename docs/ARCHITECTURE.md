# infrakt Architecture

This document describes the internal architecture of infrakt: how the layers relate to each other, how data flows through key workflows, the database schema, and the security design.

## Table of Contents

- [System Overview](#system-overview)
- [CLI Layer](#cli-layer)
- [API Layer](#api-layer)
- [Frontend Layer](#frontend-layer)
- [Core Modules](#core-modules)
- [Data Flow Diagrams](#data-flow-diagrams)
- [Database Schema](#database-schema)
- [Local File Layout](#local-file-layout)
- [Remote Server Layout](#remote-server-layout)
- [Security Architecture](#security-architecture)

---

## System Overview

infrakt has three independent entry points that all share the same underlying business logic:

```
┌──────────────────────────────────────────────────────────────────────┐
│                          Entry Points                                │
│                                                                      │
│   ┌──────────────────┐   ┌─────────────────────────────────────┐   │
│   │  infrakt (CLI)   │   │  uvicorn api.main:app (Web API)     │   │
│   │  cli/main.py     │   │  + React frontend (frontend/dist/)  │   │
│   └────────┬─────────┘   └──────────────────┬──────────────────┘   │
│            │                                 │                       │
│            └──────────────┬──────────────────┘                       │
│                           │                                          │
│               ┌───────────▼────────────────┐                        │
│               │      Shared Core Layer      │                        │
│               │  cli/core/  +  cli/models/  │                        │
│               └───────────┬────────────────┘                        │
│                           │                                          │
│               ┌───────────▼────────────────┐                        │
│               │      SSHClient (Paramiko)   │                        │
│               └───────────┬────────────────┘                        │
└───────────────────────────┼──────────────────────────────────────────┘
                            │ SSH
              ┌─────────────▼──────────────────────┐
              │        Remote Server               │
              │  Docker + Caddy + UFW + fail2ban   │
              └────────────────────────────────────┘
```

The CLI and the API are architecturally equivalent: they call the same functions in `cli/core/` with the same `SSHClient` abstraction. The key difference is execution context — the CLI runs commands synchronously in the terminal, while the API runs long-running operations (provisioning, deployment) as FastAPI background tasks.

---

## CLI Layer

The CLI is built with Click. `cli/main.py` defines the root `cli` group and the `init` command, then imports and registers five sub-groups:

```
cli (cli/main.py)
├── init
├── server (cli/commands/server.py)
│   ├── add
│   ├── list
│   ├── remove
│   ├── provision
│   ├── status
│   └── ssh
├── app (cli/commands/app.py)
│   ├── create
│   ├── deploy
│   ├── list
│   ├── logs
│   ├── restart
│   ├── stop
│   └── destroy
├── env (cli/commands/env.py)
│   ├── set
│   ├── get
│   ├── list
│   ├── delete
│   └── push
├── db (cli/commands/db.py)
│   ├── create
│   ├── destroy
│   └── list
└── proxy (cli/commands/proxy.py)
    ├── setup
    ├── add
    ├── remove
    ├── domains
    ├── status
    └── reload
```

Each command module follows the same pattern:
1. Resolve named entities (server, app) by querying the local SQLite database
2. Construct an `SSHClient` from the stored credentials
3. Call the appropriate core module function (`provision_server`, `deploy_app`, etc.)
4. Update the database with the resulting state
5. Print a result using the Rich-based console helpers

Output uses `cli/core/console.py` for consistent formatting: `info()`, `success()`, `error()`, `warning()`, `status_spinner()`, and `print_table()`.

---

## API Layer

The API is a FastAPI application (`api/main.py`) that registers six routers, all prefixed under `/api`:

```
FastAPI app (api/main.py)
├── /api/dashboard          (api/routes/dashboard.py)
├── /api/servers            (api/routes/servers.py)
├── /api/apps               (api/routes/apps.py)
├── /api/apps/{name}/env    (api/routes/env.py)
├── /api/databases          (api/routes/databases.py)
└── /api/proxy              (api/routes/proxy.py)
```

**CORS configuration:** The API allows requests from `http://localhost:5173` (Vite dev server) and `http://localhost:3000`. This is intentional — infrakt is designed for local use only.

**Background tasks:** Long-running SSH operations (provisioning, deployment, database creation) are executed as FastAPI `BackgroundTask`s. The HTTP response returns immediately with `{"message": "...", "deployment_id": N}`, and the client polls for status changes by re-fetching the resource.

**Static file serving:** In production, after running `npm run build` in the `frontend/` directory, FastAPI mounts `frontend/dist/` at the root path `/` and serves the React SPA with HTML5 history fallback. When `frontend/dist/` does not exist (development mode), the mount is skipped.

**Database initialization:** The `on_startup` event handler calls `init_db()`, which creates all SQLAlchemy tables if they don't exist. This makes the API self-bootstrapping — no separate migration step is required for a fresh install.

---

## Frontend Layer

The frontend is a React SPA built with Vite and TypeScript. It communicates exclusively with the API layer through a typed HTTP client.

```
Frontend (frontend/src/)
├── main.tsx               # React root, QueryClientProvider, BrowserRouter
├── App.tsx                # Route definitions, top-level layout
├── api/client.ts          # Typed fetch wrappers for all API endpoints
├── hooks/useApi.ts        # TanStack Query hooks wrapping client.ts
├── pages/
│   ├── Dashboard.tsx      # Platform stats + recent deployments
│   ├── Servers.tsx        # Server list + add/remove/provision
│   ├── ServerDetail.tsx   # Live metrics, apps on server, proxy routes
│   ├── Apps.tsx           # App list + create/deploy/stop/destroy
│   ├── AppDetail.tsx      # Logs, deployment history, env vars
│   └── Databases.tsx      # Database list + create/destroy
└── components/
    ├── StatusBadge.tsx    # Color-coded status pill
    ├── DataTable.tsx      # Generic sortable table
    ├── Modal.tsx          # Modal dialog wrapper
    ├── Toast.tsx          # Notification toast
    └── EmptyState.tsx     # Zero-data empty state component
```

### Data Fetching Pattern

All API calls go through `api/client.ts`, which provides a thin `fetch` wrapper that:
- Prepends `/api` to every path
- Sets `Content-Type: application/json`
- Throws a typed `ApiError(status, message)` on non-2xx responses
- Handles 204 No Content by returning `undefined`

The hooks in `hooks/useApi.ts` wrap these client functions with TanStack Query, providing:
- Automatic caching with configurable `staleTime` (default 30 seconds)
- Polling intervals: dashboard refreshes every 60 seconds, server status every 30 seconds, app logs every 15 seconds
- Optimistic cache invalidation on mutations (e.g. deploying an app invalidates the apps list and dashboard)

### Development Proxy

In development, Vite proxies all `/api/*` requests to `http://localhost:8000`, so the frontend and API can run on different ports without CORS issues.

---

## Core Modules

### `cli/core/config.py`

Defines all filesystem paths as module-level constants. Everything derives from `INFRAKT_HOME = Path.home() / ".infrakt"`:

| Constant | Path |
|----------|------|
| `INFRAKT_HOME` | `~/.infrakt/` |
| `DB_PATH` | `~/.infrakt/infrakt.db` |
| `KEYS_DIR` | `~/.infrakt/keys/` |
| `ENVS_DIR` | `~/.infrakt/envs/` |
| `MASTER_KEY_PATH` | `~/.infrakt/master.key` |

`ensure_config_dir()` creates all directories if missing. Tests monkeypatch these constants to temp directories via the `isolated_config` fixture in `tests/conftest.py`.

### `cli/core/database.py`

Manages the SQLAlchemy engine and session lifecycle. Uses a lazy-initialized module-level engine (`_engine`) and session factory (`_SessionLocal`) so the database is not touched on import.

`get_session()` is a context manager that commits on success and rolls back on exception:

```python
with get_session() as session:
    srv = session.query(Server).filter(Server.name == name).first()
    srv.status = "active"
# auto-committed here
```

`init_db()` imports all model modules (to ensure they register with `Base.metadata`) then calls `Base.metadata.create_all()`. It is idempotent — safe to call on every command invocation.

### `cli/core/ssh.py`

`SSHClient` wraps Paramiko's `SSHClient` with a higher-level interface:

| Method | Description |
|--------|-------------|
| `connect()` | Open the SSH connection. Uses key file if `key_path` is set, otherwise falls back to SSH agent / default keys |
| `run(command, timeout)` | Execute command, return `(stdout, stderr, exit_code)` |
| `run_checked(command, timeout)` | Execute command, return `stdout`. Raises `SSHConnectionError` on non-zero exit |
| `upload(local_path, remote_path)` | Upload a local file via SFTP |
| `upload_string(content, remote_path)` | Write a string directly to a remote file via SFTP |
| `download(remote_path, local_path)` | Download a remote file via SFTP |
| `read_remote_file(remote_path)` | Read a remote file and return its content as a string |
| `test_connection()` | Connect and run `echo ok`, returns `bool` |
| `close()` | Close the connection |

`SSHClient` implements the context manager protocol (`__enter__`/`__exit__`), so it is typically used as:

```python
with SSHClient(host=..., user=..., port=..., key_path=...) as ssh:
    ssh.run_checked("apt-get update")
```

The `AutoAddPolicy` is set on the underlying Paramiko client, so host key verification is not enforced. This is appropriate for a tool that provisions fresh VMs where the host key is not yet known, but it means infrakt does not protect against MITM attacks on existing known servers.

### `cli/core/provisioner.py`

`provision_server(ssh, on_step=None)` runs a fixed sequence of shell commands over SSH to set up a fresh Ubuntu server. The steps are defined as a list of `(name, command)` tuples in `PROVISION_STEPS`:

1. Update and upgrade OS packages
2. Install Docker Engine (via `get.docker.com` if not already present)
3. Install Caddy (from the official Cloudsmith APT repository if not already present)
4. Install and enable fail2ban
5. Configure UFW: deny inbound, allow 22/80/443, enable
6. Create `/opt/infrakt/{apps,caddy,backups}/`
7. Create initial `/opt/infrakt/caddy/Caddyfile`
8. Configure `/etc/caddy/Caddyfile` to import the infrakt Caddyfile, restart Caddy

Each command uses idempotency guards (`if ! command -v docker` etc.) so provisioning can be re-run safely.

The optional `on_step` callback receives `(step_name, index, total)` for progress reporting.

### `cli/core/deployer.py`

`deploy_app(ssh, app_name, *, git_repo, branch, image, port, env_content, compose_override)` handles three deployment modes:

**Git mode** (`git_repo` is set):
- If `/opt/infrakt/apps/<name>/repo/.git` exists, does `git fetch && git reset --hard origin/<branch>`
- Otherwise, clones the repository
- If the repo contains `docker-compose.yml` and no override is provided, uses it directly with `docker compose --env-file`
- Otherwise generates a minimal compose file with a `build: ./repo` context

**Image mode** (`image` is set):
- Generates a compose file with the specified image
- Runs `docker compose up -d --pull always`

**Compose override mode** (`compose_override` is set, no git or image):
- Uploads the provided compose YAML directly and runs it

All deployments:
- Create `/opt/infrakt/apps/<name>/` if it does not exist
- Upload `.env` content (decrypted in memory, sent over the encrypted SSH channel)
- Attach containers to the `infrakt` Docker network (created via `docker network create infrakt` if absent)
- Return a timestamped deployment log string that is persisted to the `Deployment` record

### `cli/core/proxy_manager.py`

Manages the Caddy reverse proxy by reading, modifying, and writing `/opt/infrakt/caddy/Caddyfile` on the remote server via SFTP, then running `systemctl reload caddy`.

The Caddyfile format used by infrakt is minimal:

```
# Managed by infrakt — do not edit manually

api.example.com {
    reverse_proxy localhost:3000
}

app.example.com {
    reverse_proxy localhost:8080
}
```

`_parse_caddyfile()` extracts `(domain, port)` tuples by scanning for `domain {` blocks containing `reverse_proxy localhost:PORT` directives. `_build_caddyfile()` regenerates the full file from the tuple list, sorted alphabetically by domain. This approach means the Caddyfile is fully rewritten on every change — external modifications to the file will be overwritten.

### `cli/core/crypto.py`

Implements Fernet symmetric encryption for environment variable storage.

`get_or_create_key()` reads `~/.infrakt/master.key` or generates a new `Fernet.generate_key()` and writes it with `chmod 0600`. This key is 32 bytes of URL-safe base64-encoded random data (256 bits of entropy in the key material, AES-128 in practice due to Fernet's internal key derivation).

**Important:** Deleting or losing `master.key` permanently loses access to all stored environment variables. There is no recovery mechanism. Back up this file.

---

## Data Flow Diagrams

### Server Provisioning

```
infrakt server provision prod-1
         │
         ▼
  Look up Server by name in SQLite
         │
         ▼
  SSHClient.connect()
         │
         ▼
  provision_server(ssh):
    ├── apt-get update && upgrade
    ├── Install Docker (if absent)
    ├── Install Caddy (if absent)
    ├── Install fail2ban
    ├── Configure UFW
    ├── mkdir /opt/infrakt/{apps,caddy,backups}
    ├── Create /opt/infrakt/caddy/Caddyfile
    └── Configure /etc/caddy/Caddyfile → import infrakt Caddyfile
         │
         ▼
  UPDATE servers SET status='active' WHERE name='prod-1'
         │
         ▼
  success("Server 'prod-1' provisioned and active")
```

### App Deployment

```
infrakt app deploy myapp
         │
         ▼
  Look up App + Server in SQLite
         │
         ▼
  INSERT INTO deployments (app_id, status='in_progress')
         │
         ▼
  Read ~/.infrakt/envs/<app_id>.json
  Decrypt each value with Fernet master key
         │
         ▼
  SSHClient.connect()
         │
         ▼
  docker network create infrakt (idempotent)
         │
         ▼
  deploy_app(ssh, ...):
    ├── mkdir -p /opt/infrakt/apps/myapp/
    ├── Upload .env (plaintext, over SSH tunnel)
    ├── [git mode] git clone or git fetch + reset
    │   └── docker compose up -d --build
    ├── [image mode] generate compose.yml
    │   └── docker compose up -d --pull always
    └── [compose mode] upload compose.yml
        └── docker compose up -d
         │
         ▼
  [if domain configured]
  add_domain(ssh, domain, port):
    ├── read /opt/infrakt/caddy/Caddyfile via SFTP
    ├── parse, upsert (domain, port) entry
    ├── write new Caddyfile via SFTP
    └── systemctl reload caddy
         │
         ▼
  UPDATE deployments SET status='success', log=..., finished_at=now()
  UPDATE apps SET status='running'
         │
         ▼
  success("App 'myapp' deployed successfully")
```

### Environment Variable Management

```
infrakt env set myapp DATABASE_URL=postgres://...
         │
         ▼
  Look up app_id in SQLite
         │
         ▼
  Load ~/.infrakt/envs/<app_id>.json (or {} if missing)
         │
         ▼
  For each KEY=VALUE:
    encrypted = Fernet(master_key).encrypt(VALUE)
    data[KEY] = encrypted
         │
         ▼
  Write ~/.infrakt/envs/<app_id>.json
         │
         ▼
  success("Set 1 variable(s) for 'myapp'")
  info("Run 'infrakt app deploy' to apply changes")

─────────────────────────────────────────────────────

infrakt env push myapp
         │
         ▼
  Look up App + Server in SQLite
         │
         ▼
  Load and decrypt all vars from ~/.infrakt/envs/<app_id>.json
         │
         ▼
  SSHClient.connect()
         │
         ▼
  SFTP upload plaintext .env to /opt/infrakt/apps/myapp/.env
         │
         ▼
  docker compose restart (in /opt/infrakt/apps/myapp/)
         │
         ▼
  success("Pushed N variable(s) to 'myapp' and restarted")
```

---

## Database Schema

infrakt uses SQLite at `~/.infrakt/infrakt.db`. There are three tables.

### `servers`

Stores registered remote servers.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-incrementing ID |
| `name` | VARCHAR(100) | UNIQUE, NOT NULL | Human-readable identifier |
| `host` | VARCHAR(255) | NOT NULL | IP address or hostname |
| `port` | INTEGER | default 22 | SSH port |
| `user` | VARCHAR(100) | default "root" | SSH username |
| `ssh_key_path` | VARCHAR(500) | nullable | Path to private key on local machine |
| `status` | VARCHAR(20) | default "inactive" | One of: `inactive`, `active`, `provisioning` |
| `provider` | VARCHAR(100) | nullable | Cloud provider label (informational only) |
| `created_at` | DATETIME | default now | Creation timestamp |
| `updated_at` | DATETIME | default now, onupdate | Last modification timestamp |

### `apps`

Stores both application deployments and database services. Database services are distinguished by `app_type` matching `db:*`.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-incrementing ID |
| `name` | VARCHAR(100) | NOT NULL | App name (unique per server) |
| `server_id` | INTEGER | FK servers.id, NOT NULL | Owning server |
| `domain` | VARCHAR(255) | nullable | Reverse proxy domain |
| `port` | INTEGER | default 3000 | Container port |
| `git_repo` | VARCHAR(500) | nullable | Git repository URL |
| `branch` | VARCHAR(100) | default "main" | Git branch |
| `image` | VARCHAR(500) | nullable | Docker image reference |
| `status` | VARCHAR(20) | default "stopped" | One of: `stopped`, `running`, `error`, `deploying` |
| `app_type` | VARCHAR(50) | default "compose" | One of: `git`, `image`, `compose`, `db:postgres`, `db:mysql`, `db:redis`, `db:mongo` |
| `created_at` | DATETIME | default now | Creation timestamp |
| `updated_at` | DATETIME | default now, onupdate | Last modification timestamp |

Unique constraint: `(name, server_id)` — the same app name can exist on different servers.

### `deployments`

Tracks individual deployment events for apps.

| Column | Type | Constraints | Description |
|--------|------|-------------|-------------|
| `id` | INTEGER | PRIMARY KEY | Auto-incrementing ID |
| `app_id` | INTEGER | FK apps.id, NOT NULL | Owning app |
| `commit_hash` | VARCHAR(40) | nullable | Git commit SHA (not yet populated automatically) |
| `status` | VARCHAR(20) | default "in_progress" | One of: `in_progress`, `success`, `failed` |
| `log` | TEXT | nullable | Full deployment log output |
| `started_at` | DATETIME | default now | Deployment start time |
| `finished_at` | DATETIME | nullable | Deployment end time (null if in progress) |

### Entity Relationships

```
servers 1──────────* apps 1──────────* deployments
```

Cascade delete: deleting a `Server` cascades to its `App` records; deleting an `App` cascades to its `Deployment` records.

---

## Local File Layout

```
~/.infrakt/
├── infrakt.db          # SQLite database (servers, apps, deployments)
├── master.key          # Fernet master key, chmod 0600
├── envs/
│   ├── 1.json          # Encrypted env vars for app_id=1
│   ├── 2.json          # Encrypted env vars for app_id=2
│   └── ...
└── keys/               # Reserved for future SSH key management
```

The `envs/<app_id>.json` files have the structure:
```json
{
  "DATABASE_URL": "gAAAAAB...<fernet token>",
  "SECRET_KEY": "gAAAAAB...<fernet token>"
}
```

---

## Remote Server Layout

After provisioning, each server has this structure under `/opt/infrakt/`:

```
/opt/infrakt/
├── apps/
│   ├── myapp/
│   │   ├── docker-compose.yml    # Generated by infrakt or from repo
│   │   ├── .env                  # Decrypted env vars, uploaded at deploy time
│   │   └── repo/                 # Git clone (git-mode apps only)
│   ├── mydb/
│   │   └── docker-compose.yml    # Generated database compose file
│   └── ...
├── caddy/
│   └── Caddyfile                 # Managed by proxy_manager, imported by Caddy
└── backups/                      # Reserved for future backup functionality
```

`/etc/caddy/Caddyfile` contains a single line:
```
import /opt/infrakt/caddy/Caddyfile
```

All containers are attached to the `infrakt` Docker bridge network, allowing inter-container communication by service name.

---

## Security Architecture

### Threat Model

infrakt is designed for use by a single developer or small team running it locally against their own infrastructure. It is not designed to be exposed to untrusted users.

### SSH Authentication

infrakt uses Paramiko's `AutoAddPolicy`, which automatically accepts unknown host keys. This is a deliberate usability trade-off for provisioning fresh VMs (where the host key is genuinely new), but it means infrakt does not protect against MITM attacks on established connections. If this is a concern, manually add the server's host key to `~/.ssh/known_hosts` and use Paramiko's `RejectPolicy` instead.

### Encryption at Rest

Env vars use Fernet (from Python's `cryptography` library), which provides:
- AES-128-CBC encryption
- HMAC-SHA256 authentication
- Timestamp inclusion (tokens have a creation time)

The master key (`~/.infrakt/master.key`) is generated once with `Fernet.generate_key()` and stored with `chmod 0600`. Anyone with access to both the master key and the `envs/` directory can decrypt all stored secrets.

### Data in Transit

All communication between infrakt and remote servers occurs over SSH (encrypted and authenticated). Environment variable plaintext is only exposed:
1. In memory on the local machine during `env push` or `app deploy`
2. Over the SSH transport layer (encrypted)
3. On the remote server's disk in `/opt/infrakt/apps/<name>/.env`

The `.env` file on the remote server is in plaintext. Access controls depend on the server's filesystem permissions. The file is owned by root and is only accessible within the Docker Compose context.

### API Security

The FastAPI API has no authentication. It is intended to be run locally (`localhost:8000`) and accessed only by the local React frontend or by the developer directly. Do not expose the API to a public network.

CORS is configured to allow `http://localhost:5173` and `http://localhost:3000` only. If you expose the API on a non-localhost interface, update the `allow_origins` list in `api/main.py` appropriately and add authentication middleware.

### Server Hardening

The provisioning step applies these security controls:

| Control | Configuration |
|---------|---------------|
| UFW | Deny all inbound except 22 (SSH), 80 (HTTP), 443 (HTTPS) |
| fail2ban | Default SSH jail: bans IPs after repeated failed login attempts |
| Database ports | Bound to `127.0.0.1` only — never accessible from the internet |
| Caddy TLS | Automatic certificate provisioning and renewal via Let's Encrypt ACME |
