# infrakt REST API Reference

The infrakt API is a FastAPI application that exposes the same operations as the CLI over HTTP. It is used by the React web dashboard and can be called directly with curl or any HTTP client.

## Base URL and Authentication

**Base URL:** `http://localhost:8000/api`

**Authentication:** None. The API is designed for local use only. Do not expose it on a public network interface without adding authentication middleware.

**Content-Type:** All request and response bodies use `application/json`.

**Interactive docs:** `http://localhost:8000/docs` (Swagger UI) and `http://localhost:8000/redoc` (ReDoc) are available when the server is running.

## Starting the API

```bash
uvicorn api.main:app --reload --port 8000
```

The API initializes the SQLite database on startup. No separate migration step is required.

## Error Response Format

All errors return a JSON body with a `detail` field:

```json
{
  "detail": "Server 'prod-1' not found"
}
```

HTTP status codes follow standard conventions:

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 201 | Resource created |
| 400 | Bad request (validation error or duplicate resource) |
| 404 | Resource not found |
| 422 | Request body validation failed (Pydantic) |
| 502 | Cannot reach remote server via SSH |
| 500 | Unexpected server error |

---

## Dashboard

### `GET /api/dashboard`

Returns platform-wide statistics and the 10 most recent deployments.

**Response: `200 OK`**

```json
{
  "total_servers": 3,
  "active_servers": 2,
  "total_apps": 7,
  "running_apps": 5,
  "total_databases": 2,
  "recent_deployments": [
    {
      "id": 42,
      "app_id": 7,
      "commit_hash": null,
      "status": "success",
      "log": "[2024-01-15T10:00:00] Starting deployment...",
      "started_at": "2024-01-15T10:00:00",
      "finished_at": "2024-01-15T10:01:23"
    }
  ]
}
```

**Example:**

```bash
curl http://localhost:8000/api/dashboard
```

---

## Servers

### `GET /api/servers`

List all registered servers, ordered by name.

**Response: `200 OK`** — array of server objects

```json
[
  {
    "id": 1,
    "name": "prod-1",
    "host": "1.2.3.4",
    "user": "root",
    "port": 22,
    "ssh_key_path": "/Users/you/.ssh/id_ed25519",
    "status": "active",
    "provider": "hetzner",
    "created_at": "2024-01-10T09:00:00",
    "updated_at": "2024-01-10T09:05:00",
    "app_count": 3
  }
]
```

**Server status values:** `inactive`, `active`, `provisioning`

**Example:**

```bash
curl http://localhost:8000/api/servers
```

---

### `POST /api/servers`

Register a new server. Tests SSH connectivity after creation.

**Request body:**

```json
{
  "name": "prod-1",
  "host": "1.2.3.4",
  "user": "root",
  "port": 22,
  "ssh_key_path": "/Users/you/.ssh/id_ed25519",
  "provider": "hetzner"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | Unique server name |
| `host` | string | yes | — | IP address or hostname |
| `user` | string | no | `"root"` | SSH username |
| `port` | integer | no | `22` | SSH port |
| `ssh_key_path` | string | no | `null` | Path to SSH private key on local machine |
| `provider` | string | no | `null` | Cloud provider label (informational) |

**Response: `201 Created`** — server object (same shape as GET)

**Errors:**
- `400` — server name already exists

**Example:**

```bash
curl -X POST http://localhost:8000/api/servers \
  -H "Content-Type: application/json" \
  -d '{"name": "prod-1", "host": "1.2.3.4", "ssh_key_path": "~/.ssh/id_ed25519"}'
```

---

### `DELETE /api/servers/{name}`

Remove a registered server from the local database. Does not touch the remote server. Cascades to delete all associated apps and deployments.

**Path parameters:**

| Parameter | Description |
|-----------|-------------|
| `name` | Server name |

**Response: `200 OK`**

```json
{
  "message": "Server 'prod-1' removed"
}
```

**Errors:**
- `404` — server not found

**Example:**

```bash
curl -X DELETE http://localhost:8000/api/servers/prod-1
```

---

### `POST /api/servers/{name}/provision`

Provision a server in the background. Installs Docker, Caddy, UFW, and fail2ban via SSH. Returns immediately; the server's `status` field transitions from `inactive` → `provisioning` → `active` (or back to `inactive` on failure).

**Response: `200 OK`**

```json
{
  "message": "Provisioning started for 'prod-1'"
}
```

**Errors:**
- `404` — server not found

**Example:**

```bash
curl -X POST http://localhost:8000/api/servers/prod-1/provision
```

Poll `GET /api/servers` to check when status becomes `active`.

---

### `GET /api/servers/{name}/status`

Fetch live system metrics from the server over SSH. This call connects to the server and runs commands — it may take a few seconds.

**Response: `200 OK`**

```json
{
  "name": "prod-1",
  "host": "1.2.3.4",
  "uptime": "up 5 days, 3 hours",
  "memory": "1.2G/3.8G",
  "disk": "12G/40G (30% used)",
  "containers": "infrakt-myapp\tUp 2 hours\ninfra-caddy\tUp 5 days"
}
```

**Errors:**
- `404` — server not found
- `502` — SSH connection failed

**Example:**

```bash
curl http://localhost:8000/api/servers/prod-1/status
```

---

### `POST /api/servers/{name}/test`

Test SSH connectivity to the server.

**Response: `200 OK`**

```json
{
  "reachable": true
}
```

**Errors:**
- `404` — server not found

**Example:**

```bash
curl -X POST http://localhost:8000/api/servers/prod-1/test
```

---

## Apps

### `GET /api/apps`

List all apps, optionally filtered by server.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `server` | string | Filter by server name |

**Response: `200 OK`** — array of app objects

```json
[
  {
    "id": 1,
    "name": "myapp",
    "server_id": 1,
    "server_name": "prod-1",
    "domain": "myapp.example.com",
    "port": 3000,
    "git_repo": "https://github.com/you/myapp",
    "branch": "main",
    "image": null,
    "status": "running",
    "app_type": "git",
    "created_at": "2024-01-10T10:00:00",
    "updated_at": "2024-01-10T10:05:00"
  }
]
```

**App status values:** `stopped`, `running`, `error`, `deploying`

**App type values:** `git`, `image`, `compose`

**Note:** Database services (`app_type` matching `db:*`) are excluded from this endpoint. Use `GET /api/databases` for those.

**Example:**

```bash
curl http://localhost:8000/api/apps
curl "http://localhost:8000/api/apps?server=prod-1"
```

---

### `POST /api/apps`

Register a new app on a server.

**Request body:**

```json
{
  "name": "myapp",
  "server_name": "prod-1",
  "domain": "myapp.example.com",
  "port": 3000,
  "git_repo": "https://github.com/you/myapp",
  "branch": "main",
  "image": null
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `name` | string | yes | — | App name (unique per server) |
| `server_name` | string | yes | — | Target server name |
| `domain` | string | no | `null` | Domain for reverse proxy |
| `port` | integer | no | `3000` | Container port the app listens on |
| `git_repo` | string | no | `null` | Git repository URL |
| `branch` | string | no | `"main"` | Git branch |
| `image` | string | no | `null` | Docker image (e.g. `nginx:alpine`) |

App type is inferred: `image` if `image` is set, `git` if `git_repo` is set, otherwise `compose`.

**Response: `201 Created`** — app object

**Errors:**
- `404` — server not found
- `400` — app name already exists on the server

**Example:**

```bash
curl -X POST http://localhost:8000/api/apps \
  -H "Content-Type: application/json" \
  -d '{"name": "myapp", "server_name": "prod-1", "git_repo": "https://github.com/you/myapp", "port": 3000}'
```

---

### `POST /api/apps/{name}/deploy`

Deploy or redeploy an app in the background. Creates a `Deployment` record immediately and runs the deployment asynchronously.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `server` | string | Server name (optional if app name is unique) |

**Response: `200 OK`**

```json
{
  "message": "Deployment started for 'myapp'",
  "deployment_id": 42
}
```

**Errors:**
- `404` — app not found

Poll `GET /api/apps/{name}/deployments` to check deployment status.

**Example:**

```bash
curl -X POST http://localhost:8000/api/apps/myapp/deploy
```

---

### `GET /api/apps/{name}/logs`

Fetch container logs from the remote server over SSH.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `server` | string | — | Server name (optional) |
| `lines` | integer | `100` | Number of log lines to retrieve |

**Response: `200 OK`**

```json
{
  "app_name": "myapp",
  "logs": "myapp-1  | 2024-01-15 10:00:00 Server listening on port 3000\n..."
}
```

**Errors:**
- `404` — app not found
- `502` — SSH connection failed

**Example:**

```bash
curl "http://localhost:8000/api/apps/myapp/logs?lines=200"
```

---

### `GET /api/apps/{name}/deployments`

List the 20 most recent deployments for an app, newest first.

**Response: `200 OK`** — array of deployment objects

```json
[
  {
    "id": 42,
    "app_id": 1,
    "commit_hash": null,
    "status": "success",
    "log": "[2024-01-15T10:00:00] Starting deployment...\n[2024-01-15T10:01:23] Deployment complete",
    "started_at": "2024-01-15T10:00:00",
    "finished_at": "2024-01-15T10:01:23"
  }
]
```

**Deployment status values:** `in_progress`, `success`, `failed`

**Errors:**
- `404` — app not found

**Example:**

```bash
curl http://localhost:8000/api/apps/myapp/deployments
```

---

### `POST /api/apps/{name}/restart`

Restart the app's Docker Compose services without redeploying.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `server` | string | Server name (optional) |

**Response: `200 OK`**

```json
{
  "message": "App 'myapp' restarted"
}
```

**Errors:**
- `404` — app not found

**Example:**

```bash
curl -X POST http://localhost:8000/api/apps/myapp/restart
```

---

### `POST /api/apps/{name}/stop`

Stop the app's containers. Sets status to `stopped`.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `server` | string | Server name (optional) |

**Response: `200 OK`**

```json
{
  "message": "App 'myapp' stopped"
}
```

**Errors:**
- `404` — app not found

**Example:**

```bash
curl -X POST http://localhost:8000/api/apps/myapp/stop
```

---

### `DELETE /api/apps/{name}`

Destroy an app: stop containers, remove volumes, delete `/opt/infrakt/apps/<name>/`, and remove the Caddy proxy route. Removes the app record from the database.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `server` | string | Server name (optional) |

**Response: `200 OK`**

```json
{
  "message": "App 'myapp' destroyed"
}
```

**Errors:**
- `404` — app not found

**Warning:** This operation is irreversible and deletes all app data on the server.

**Example:**

```bash
curl -X DELETE http://localhost:8000/api/apps/myapp
```

---

## Environment Variables

Env var endpoints are nested under `/api/apps/{app_name}/env`. Variables are stored encrypted locally; the API decrypts them on demand.

### `GET /api/apps/{app_name}/env`

List all environment variables for an app. Values are masked by default.

**Query parameters:**

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `show_values` | boolean | `false` | Return decrypted plaintext values |

**Response: `200 OK`** — array of env var objects (sorted by key)

```json
[
  {
    "key": "DATABASE_URL",
    "value": "••••••••"
  },
  {
    "key": "SECRET_KEY",
    "value": "••••••••"
  }
]
```

With `show_values=true`:

```json
[
  {
    "key": "DATABASE_URL",
    "value": "postgres://mydb:password@localhost:5432/mydb"
  }
]
```

**Errors:**
- `404` — app not found

**Example:**

```bash
curl "http://localhost:8000/api/apps/myapp/env"
curl "http://localhost:8000/api/apps/myapp/env?show_values=true"
```

---

### `POST /api/apps/{app_name}/env`

Set one or more environment variables. Encrypts values before storing.

**Request body:** array of `{key, value}` objects

```json
[
  {"key": "DATABASE_URL", "value": "postgres://mydb:password@localhost:5432/mydb"},
  {"key": "SECRET_KEY", "value": "abc123"}
]
```

**Response: `200 OK`** — array of the set variables with masked values

```json
[
  {"key": "DATABASE_URL", "value": "••••••••"},
  {"key": "SECRET_KEY", "value": "••••••••"}
]
```

**Errors:**
- `404` — app not found

After setting variables, call `POST /api/apps/{name}/deploy` or `POST /api/apps/{name}/env/push` to apply them to the running container.

**Example:**

```bash
curl -X POST "http://localhost:8000/api/apps/myapp/env" \
  -H "Content-Type: application/json" \
  -d '[{"key": "DATABASE_URL", "value": "postgres://localhost/mydb"}]'
```

---

### `DELETE /api/apps/{app_name}/env/{key}`

Delete a single environment variable.

**Path parameters:**

| Parameter | Description |
|-----------|-------------|
| `app_name` | App name |
| `key` | Environment variable name |

**Response: `200 OK`**

```json
{
  "message": "Deleted 'OLD_SECRET'"
}
```

**Errors:**
- `404` — app or variable not found

**Example:**

```bash
curl -X DELETE "http://localhost:8000/api/apps/myapp/env/OLD_SECRET"
```

---

### `POST /api/apps/{app_name}/env/push`

Push all decrypted environment variables to the server and restart the app containers. Equivalent to `infrakt env push`.

**Response: `200 OK`**

```json
{
  "message": "Pushed 3 variable(s) and restarted"
}
```

**Errors:**
- `404` — app not found

**Example:**

```bash
curl -X POST "http://localhost:8000/api/apps/myapp/env/push"
```

---

## Databases

### `GET /api/databases`

List all database services, optionally filtered by server.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `server` | string | Filter by server name |

**Response: `200 OK`** — array of database objects

```json
[
  {
    "id": 5,
    "name": "mydb",
    "server_name": "prod-1",
    "db_type": "postgres",
    "port": 5432,
    "status": "running"
  }
]
```

**Database type values:** `postgres`, `mysql`, `redis`, `mongo`

**Example:**

```bash
curl http://localhost:8000/api/databases
curl "http://localhost:8000/api/databases?server=prod-1"
```

---

### `POST /api/databases`

Create a database service on a server in the background. Returns immediately with the connection string. The password is not stored by infrakt — save it immediately.

**Request body:**

```json
{
  "server_name": "prod-1",
  "name": "mydb",
  "db_type": "postgres",
  "version": "16"
}
```

| Field | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `server_name` | string | yes | — | Target server name |
| `name` | string | yes | — | Database service name |
| `db_type` | string | yes | — | One of: `postgres`, `mysql`, `redis`, `mongo` |
| `version` | string | no | latest stable | Image version tag |

Default versions: Postgres 16, MySQL 8, Redis 7-alpine, MongoDB 7.

**Response: `201 Created`**

```json
{
  "message": "Creating postgres database 'mydb'",
  "password": "rAnD0mP4ssw0rd24chars"
}
```

**Errors:**
- `400` — unsupported `db_type` or service name already exists on server
- `404` — server not found

**Connection strings by type:**

| Type | Format |
|------|--------|
| postgres | `postgresql://<name>:<password>@localhost:5432/<name>` |
| mysql | `mysql://<name>:<password>@localhost:3306/<name>` |
| redis | `redis://localhost:6379` |
| mongo | `mongodb://<name>:<password>@localhost:27017` |

**Example:**

```bash
curl -X POST http://localhost:8000/api/databases \
  -H "Content-Type: application/json" \
  -d '{"server_name": "prod-1", "name": "mydb", "db_type": "postgres"}'
```

---

### `DELETE /api/databases/{name}`

Destroy a database service: stop containers, remove all data volumes, and delete the app directory. Removes the database record from the local database.

**Query parameters:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `server` | string | Server name (optional if name is unique) |

**Response: `200 OK`**

```json
{
  "message": "Database 'mydb' destroyed"
}
```

**Errors:**
- `404` — database not found

**Warning:** This permanently deletes all database data.

**Example:**

```bash
curl -X DELETE "http://localhost:8000/api/databases/mydb?server=prod-1"
```

---

## Proxy

### `GET /api/proxy/{server_name}/domains`

List all active reverse proxy routes on a server. Reads the Caddyfile from the remote server over SSH.

**Response: `200 OK`** — array of proxy route objects

```json
[
  {
    "domain": "api.example.com",
    "port": 3000
  },
  {
    "domain": "app.example.com",
    "port": 8080
  }
]
```

**Errors:**
- `404` — server not found

**Example:**

```bash
curl http://localhost:8000/api/proxy/prod-1/domains
```

---

### `POST /api/proxy/routes`

Add a reverse proxy route on a server. Modifies the Caddyfile on the remote server and reloads Caddy.

**Request body:**

```json
{
  "domain": "api.example.com",
  "port": 3000,
  "server_name": "prod-1"
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `domain` | string | yes | Domain to proxy |
| `port` | integer | yes | Local port to forward to |
| `server_name` | string | yes | Target server name |

**Response: `201 Created`**

```json
{
  "message": "Added api.example.com -> localhost:3000"
}
```

**Errors:**
- `404` — server not found

**Example:**

```bash
curl -X POST http://localhost:8000/api/proxy/routes \
  -H "Content-Type: application/json" \
  -d '{"domain": "api.example.com", "port": 3000, "server_name": "prod-1"}'
```

---

### `DELETE /api/proxy/{server_name}/domains/{domain}`

Remove a reverse proxy route. Modifies the Caddyfile on the remote server and reloads Caddy.

**Response: `200 OK`**

```json
{
  "message": "Removed api.example.com"
}
```

**Errors:**
- `404` — server not found

**Example:**

```bash
curl -X DELETE "http://localhost:8000/api/proxy/prod-1/domains/api.example.com"
```

---

### `GET /api/proxy/{server_name}/status`

Get the systemd status of the Caddy service on the server.

**Response: `200 OK`**

```json
{
  "status": "● caddy.service - Caddy\n   Loaded: loaded (/lib/systemd/system/caddy.service)\n   Active: active (running)..."
}
```

**Errors:**
- `404` — server not found

**Example:**

```bash
curl http://localhost:8000/api/proxy/prod-1/status
```

---

### `POST /api/proxy/{server_name}/reload`

Trigger a graceful Caddy configuration reload (`systemctl reload caddy`).

**Response: `200 OK`**

```json
{
  "message": "Caddy reloaded"
}
```

**Errors:**
- `404` — server not found

**Example:**

```bash
curl -X POST http://localhost:8000/api/proxy/prod-1/reload
```
