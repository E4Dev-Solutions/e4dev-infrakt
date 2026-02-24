# infrakt CLI Command Reference

Complete reference for all `infrakt` commands, subcommands, options, and usage examples.

**Version:** 0.1.0

## Global Options

```bash
infrakt --version   # print version and exit
infrakt --help      # show top-level help
infrakt <command> --help  # show help for a specific command
```

## Command Groups

- [`init`](#init) — Initialize config and database
- [`server`](#server) — Manage remote servers
- [`app`](#app) — Manage application deployments
- [`env`](#env) — Manage app environment variables
- [`db`](#db) — Manage database services
- [`proxy`](#proxy) — Manage the Caddy reverse proxy

---

## `init`

Initialize the infrakt configuration directory and database. Run this once before using any other command.

```bash
infrakt init
```

**What it does:**
- Creates `~/.infrakt/` and subdirectories (`envs/`, `keys/`)
- Creates `~/.infrakt/infrakt.db` (SQLite, all tables)
- Generates `~/.infrakt/master.key` (Fernet encryption key, `chmod 0600`) if it does not exist

**Output:**
```
✓ Initialized infrakt at /Users/you/.infrakt
```

Running `init` multiple times is safe — it will not overwrite an existing database or key.

---

## `server`

Manage remote servers registered with infrakt.

### `server add`

Register a new server and verify SSH connectivity.

```bash
infrakt server add [OPTIONS]
```

**Options:**

| Option | Type | Default | Required | Description |
|--------|------|---------|----------|-------------|
| `--name` | text | prompted | yes | Unique identifier for the server |
| `--host` | text | prompted | yes | IP address or hostname |
| `--user` | text | `root` | no | SSH login username |
| `--port` | integer | `22` | no | SSH port number |
| `--key` | path | none | no | Path to SSH private key file |
| `--provider` | text | none | no | Cloud provider label (informational; e.g. `hetzner`, `digitalocean`, `aws`) |

If `--name` or `--host` are omitted, you will be prompted for them interactively.

**Examples:**

```bash
# Minimal — prompts for name and host
infrakt server add

# Key-based auth on standard port
infrakt server add --name prod-1 --host 1.2.3.4 --key ~/.ssh/id_ed25519

# Non-root user, non-standard port, provider label
infrakt server add \
  --name staging \
  --host staging.example.com \
  --user deploy \
  --port 2222 \
  --key ~/.ssh/id_rsa \
  --provider digitalocean
```

**Output:**

```
ℹ Testing SSH connection to root@1.2.3.4:22...
✓ Server 'prod-1' added and SSH connection verified
```

If SSH fails, the server is still saved with a warning — connectivity issues can be resolved later.

---

### `server list`

List all registered servers.

```bash
infrakt server list
```

Displays a table with columns: Name, Host, User, Port, Status, Provider.

**Status values:** `inactive`, `active`, `provisioning`

**Example output:**

```
          Servers
 Name    Host      User  Port  Status  Provider
 prod-1  1.2.3.4   root  22    active  hetzner
 staging 5.6.7.8   root  22    inactive digitalocean
```

---

### `server remove`

Remove a server from the local database. Does not interact with the remote server.

```bash
infrakt server remove <name> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `name` | Server name to remove |

**Options:**

| Option | Description |
|--------|-------------|
| `--force` | Skip the confirmation prompt when the server has registered apps |

**Examples:**

```bash
infrakt server remove prod-1           # prompts if server has apps
infrakt server remove old-server --force  # no prompt
```

Removing a server cascades to delete all associated app records and their deployment histories from the local database.

---

### `server provision`

Provision a server with the infrakt stack via SSH. Requires the server to be reachable over SSH as a root-equivalent user.

```bash
infrakt server provision <name>
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `name` | Server name (must be registered with `server add` first) |

**What gets installed and configured:**

1. OS packages: `apt-get update && apt-get upgrade`
2. Docker Engine (via `https://get.docker.com`, skipped if already installed)
3. Caddy web server (from official Cloudsmith APT repo, skipped if already installed)
4. fail2ban (SSH brute-force protection)
5. UFW firewall: deny all inbound, allow ports 22, 80, 443
6. Directory structure: `/opt/infrakt/{apps,caddy,backups}/`
7. Initial Caddyfile at `/opt/infrakt/caddy/Caddyfile`
8. Caddy configured to import the infrakt Caddyfile

Sets server status to `active` on success.

**Examples:**

```bash
infrakt server provision prod-1
```

**Note:** This command typically takes 2–5 minutes on a fresh server. It is safe to re-run — all installation steps are idempotent.

---

### `server status`

Show live system metrics from a server.

```bash
infrakt server status <name>
```

Connects via SSH and runs: `uptime -p`, `free -h`, `df -h /`, `docker ps`.

**Example output:**

```
ℹ Server: prod-1 (1.2.3.4)
ℹ Uptime: up 3 days, 12 hours
ℹ Memory: 1.2G/3.8G
ℹ Disk:   12G/40G (30% used)
ℹ Containers:
infrakt-myapp	Up 2 hours
infrakt-db-mydb	Up 3 days
```

---

### `server ssh`

Open an interactive SSH session to a server using the registered credentials.

```bash
infrakt server ssh <name>
```

Equivalent to running `ssh [-i <key>] <user>@<host> -p <port>` with the stored credentials. Delegates to the system `ssh` binary.

**Example:**

```bash
infrakt server ssh prod-1
# opens interactive shell on prod-1
```

---

## `app`

Manage application deployments.

### `app create`

Register a new app on a server. This only creates the database record — it does not deploy anything. Use `app deploy` after creating.

```bash
infrakt app create [OPTIONS]
```

**Options:**

| Option | Type | Default | Required | Description |
|--------|------|---------|----------|-------------|
| `--server` | text | — | yes | Target server name |
| `--name` | text | — | yes | App name (must be unique per server) |
| `--domain` | text | none | no | Domain for the reverse proxy (e.g. `api.example.com`) |
| `--port` | integer | `3000` | no | Container port the app listens on |
| `--git` | url | none | no | Git repository URL |
| `--branch` | text | `main` | no | Git branch to deploy |
| `--image` | text | none | no | Docker image (e.g. `nginx:alpine`, `myrepo/myapp:latest`) |

App type is inferred from the options provided:
- `--image` set → type `image`
- `--git` set → type `git`
- neither → type `compose` (you must provide your own `docker-compose.yml` via deploy)

**Examples:**

```bash
# Image-based app
infrakt app create \
  --server prod-1 \
  --name web \
  --image nginx:alpine \
  --domain web.example.com \
  --port 80

# Git-based app (repo must contain a Dockerfile or docker-compose.yml)
infrakt app create \
  --server prod-1 \
  --name api \
  --git https://github.com/you/api.git \
  --branch production \
  --domain api.example.com \
  --port 3000

# App with no domain (internal service, not exposed via Caddy)
infrakt app create --server prod-1 --name worker --image myworker:latest
```

---

### `app deploy`

Deploy or redeploy an app. Creates a deployment record, runs the appropriate Docker Compose workflow on the server, and configures the Caddy proxy if a domain is set.

```bash
infrakt app deploy <name> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `name` | App name |

**Options:**

| Option | Type | Description |
|--------|------|-------------|
| `--server` | text | Server name — only needed if the app name is not unique across all servers |

**Deployment workflow by app type:**

**Git apps** (`--git` was set at create time):
- If the repo is already cloned: `git fetch && git reset --hard origin/<branch>`
- If not: `git clone -b <branch> <url> /opt/infrakt/apps/<name>/repo`
- If `docker-compose.yml` exists in the repo root: runs `docker compose --env-file ../.env up -d --build`
- Otherwise: generates a minimal compose file with `build: ./repo`

**Image apps** (`--image` was set at create time):
- Generates a compose file with the image
- Runs `docker compose up -d --pull always` (always pulls latest)

All deployments:
- Create `/opt/infrakt/apps/<name>/` on the server
- Upload decrypted env vars as `.env`
- Ensure the `infrakt` Docker network exists
- Configure Caddy reverse proxy if a domain is configured

**Examples:**

```bash
infrakt app deploy myapp
infrakt app deploy myapp --server prod-1
```

**Output:**

```
✓ App 'myapp' deployed successfully
```

On failure, the deployment record is marked `failed` with the error message in the log.

---

### `app list`

List all apps across all servers.

```bash
infrakt app list [OPTIONS]
```

**Options:**

| Option | Type | Description |
|--------|------|-------------|
| `--server` | text | Filter by server name |

**Example output:**

```
                        Apps
 Name   Server  Domain                Port  Status   Type
 api    prod-1  api.example.com       3000  running  git
 web    prod-1  web.example.com       80    running  image
 worker staging —                     —     stopped  image
```

Database services are excluded from this list. Use `infrakt db list` for those.

---

### `app logs`

Retrieve container logs from the remote server.

```bash
infrakt app logs <name> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `name` | App name |

**Options:**

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--lines` | integer | `100` | Number of log lines to retrieve |
| `--server` | text | — | Filter by server name |

**Examples:**

```bash
infrakt app logs myapp
infrakt app logs myapp --lines 500
infrakt app logs myapp --server prod-1 --lines 50
```

Outputs the raw `docker compose logs --tail=<lines>` output from the server.

---

### `app restart`

Restart the app's Docker Compose services without redeploying.

```bash
infrakt app restart <name> [OPTIONS]
```

**Options:**

| Option | Type | Description |
|--------|------|-------------|
| `--server` | text | Filter by server name |

**Examples:**

```bash
infrakt app restart myapp
```

Runs `docker compose restart` in `/opt/infrakt/apps/<name>/` on the server.

---

### `app stop`

Stop the app's containers.

```bash
infrakt app stop <name> [OPTIONS]
```

**Options:**

| Option | Type | Description |
|--------|------|-------------|
| `--server` | text | Filter by server name |

**Examples:**

```bash
infrakt app stop myapp
```

Runs `docker compose down` in `/opt/infrakt/apps/<name>/` and sets the app status to `stopped` in the local database.

---

### `app destroy`

Permanently destroy an app: stop containers, remove volumes, delete all files, remove the Caddy proxy route. Removes the app record from the local database.

```bash
infrakt app destroy <name> [OPTIONS]
```

**Options:**

| Option | Type | Description |
|--------|------|-------------|
| `--server` | text | Filter by server name |
| `--force` | flag | Skip the confirmation prompt |

**Examples:**

```bash
infrakt app destroy myapp           # prompts: "Destroy app 'myapp' and all its data?"
infrakt app destroy myapp --force   # no prompt
```

**Warning:** This deletes all app data on the server including any volumes. This cannot be undone.

---

## `env`

Manage environment variables for apps. Variables are encrypted with Fernet and stored locally at `~/.infrakt/envs/<app_id>.json`. They are only decrypted immediately before being sent to the server.

Changes to env vars do not take effect on the running app until you run `infrakt app deploy <name>` or `infrakt env push <name>`.

### `env set`

Set one or more environment variables.

```bash
infrakt env set <app_name> <KEY=VALUE> [<KEY=VALUE> ...] [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `app_name` | App name |
| `KEY=VALUE` | One or more `KEY=VALUE` pairs (at least one required) |

**Options:**

| Option | Type | Description |
|--------|------|-------------|
| `--server` | text | Filter by server name |

**Examples:**

```bash
# Set a single variable
infrakt env set myapp DATABASE_URL=postgres://localhost/mydb

# Set multiple variables at once
infrakt env set myapp \
  DATABASE_URL=postgres://localhost/mydb \
  SECRET_KEY=abc123 \
  DEBUG=false \
  PORT=3000
```

Values containing spaces or special shell characters should be quoted:

```bash
infrakt env set myapp "MESSAGE=hello world"
infrakt env set myapp "CONNECTION=host=localhost port=5432 dbname=mydb"
```

---

### `env get`

Print the decrypted value of a single variable.

```bash
infrakt env get <app_name> <KEY> [OPTIONS]
```

**Examples:**

```bash
infrakt env get myapp DATABASE_URL
# postgres://localhost/mydb

infrakt env get myapp SECRET_KEY --server prod-1
```

---

### `env list`

List all environment variable keys for an app. Values are masked by default.

```bash
infrakt env list <app_name> [OPTIONS]
```

**Options:**

| Option | Description |
|--------|-------------|
| `--show-values` | Decrypt and display plaintext values |
| `--server` | Filter by server name |

**Examples:**

```bash
infrakt env list myapp
# Shows: DATABASE_URL  ••••••••
#        SECRET_KEY    ••••••••

infrakt env list myapp --show-values
# Shows: DATABASE_URL  postgres://localhost/mydb
#        SECRET_KEY    abc123
```

---

### `env delete`

Delete a single environment variable from local storage.

```bash
infrakt env delete <app_name> <KEY> [OPTIONS]
```

**Options:**

| Option | Type | Description |
|--------|------|-------------|
| `--server` | text | Filter by server name |

**Examples:**

```bash
infrakt env delete myapp OLD_SECRET
```

This only removes the variable from local storage. The `.env` file on the server is not updated until you run `infrakt app deploy` or `infrakt env push`.

---

### `env push`

Write all decrypted environment variables directly to the server and restart the app.

```bash
infrakt env push <app_name> [OPTIONS]
```

**Options:**

| Option | Type | Description |
|--------|------|-------------|
| `--server` | text | Filter by server name |

**Examples:**

```bash
infrakt env push myapp
```

Uploads the decrypted `.env` file to `/opt/infrakt/apps/<name>/.env` via SFTP, then runs `docker compose restart`.

Use this instead of `infrakt app deploy` when you only want to update env vars without triggering a full redeploy (git pull + docker build).

---

## `db`

Manage database services on servers. Databases run as Docker Compose services within the `infrakt` Docker network and are bound to `127.0.0.1` only — they are not accessible from the internet.

**Supported types:**

| Type | Default Version | Port |
|------|-----------------|------|
| `postgres` | 16 | 5432 |
| `mysql` | 8 | 3306 |
| `redis` | 7-alpine | 6379 |
| `mongo` | 7 | 27017 |

### `db create`

Create and start a database service on a server. Generates a random password using `secrets.token_urlsafe(24)` (144 bits of entropy). Prints the connection string once — save it, because infrakt does not store the password.

```bash
infrakt db create [OPTIONS]
```

**Options:**

| Option | Type | Required | Default | Description |
|--------|------|----------|---------|-------------|
| `--server` | text | yes | — | Target server name |
| `--name` | text | yes | — | Database service name |
| `--type` | choice | yes | — | One of: `postgres`, `mysql`, `redis`, `mongo` |
| `--version` | text | no | latest stable | Image version tag |

**Examples:**

```bash
infrakt db create --server prod-1 --name mydb --type postgres
# ✓ Database 'mydb' (postgres) created on 'prod-1'
# ℹ Connection string: postgresql://mydb:<password>@localhost:5432/mydb
# ℹ Save this connection string — the password is not stored locally.

infrakt db create --server prod-1 --name cache --type redis

infrakt db create --server prod-1 --name analytics --type postgres --version 15
```

**Workflow after creating a database:**

Add the connection string to your app's env vars so it can connect:

```bash
infrakt env set myapp DATABASE_URL=postgresql://mydb:<password>@localhost:5432/mydb
infrakt app deploy myapp
```

The app container and the database container are both on the `infrakt` Docker network, so `localhost` in the connection string refers to the Docker host's loopback interface (the database port is bound to `127.0.0.1`).

---

### `db destroy`

Stop a database service, remove all data volumes, and delete the service directory.

```bash
infrakt db destroy <name> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `name` | Database service name |

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--server` | yes | Server name |
| `--force` | no | Skip confirmation prompt |

**Examples:**

```bash
infrakt db destroy mydb --server prod-1
infrakt db destroy mydb --server prod-1 --force
```

**Warning:** This permanently deletes all database data. There is no undo.

---

### `db list`

List all database services.

```bash
infrakt db list [OPTIONS]
```

**Options:**

| Option | Type | Description |
|--------|------|-------------|
| `--server` | text | Filter by server name |

**Example output:**

```
                  Databases
 Name    Server  Type      Port  Status
 mydb    prod-1  postgres  5432  running
 cache   prod-1  redis     6379  running
```

---

## `proxy`

Manage the Caddy reverse proxy. Caddy is configured during `infrakt server provision` and manages TLS certificates automatically via Let's Encrypt. The Caddyfile lives at `/opt/infrakt/caddy/Caddyfile` on each server.

Proxy routes are configured automatically when you set `--domain` on an app and deploy it. Use these commands for manual management.

### `proxy setup`

Initialize Caddy configuration on a server. This runs automatically during `infrakt server provision`. Only use it manually if you need to re-initialize a server's Caddy configuration.

```bash
infrakt proxy setup <server_name>
```

**Examples:**

```bash
infrakt proxy setup prod-1
```

---

### `proxy add`

Manually add a reverse proxy route.

```bash
infrakt proxy add <domain> [OPTIONS]
```

**Arguments:**

| Argument | Description |
|----------|-------------|
| `domain` | Fully-qualified domain name to proxy |

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--server` | yes | Server name |
| `--port` | yes | Local port to forward traffic to |

**Examples:**

```bash
infrakt proxy add api.example.com --server prod-1 --port 3000
infrakt proxy add app.example.com --server prod-1 --port 8080
```

Caddy will automatically obtain a TLS certificate for the domain via ACME. The domain must have a DNS `A` record pointing to the server's IP.

---

### `proxy remove`

Remove a reverse proxy route.

```bash
infrakt proxy remove <domain> [OPTIONS]
```

**Options:**

| Option | Required | Description |
|--------|----------|-------------|
| `--server` | yes | Server name |

**Examples:**

```bash
infrakt proxy remove old-app.example.com --server prod-1
```

---

### `proxy domains`

List all active proxy routes on a server.

```bash
infrakt proxy domains <server_name>
```

Reads the Caddyfile from the remote server and parses all `reverse_proxy` blocks.

**Example output:**

```
         Proxy Routes
 Domain                Port
 api.example.com       3000
 app.example.com       8080
```

---

### `proxy status`

Show the systemd status of the Caddy service.

```bash
infrakt proxy status <server_name>
```

**Example:**

```bash
infrakt proxy status prod-1
# Outputs systemctl status caddy output
```

---

### `proxy reload`

Trigger a graceful Caddy configuration reload without restarting.

```bash
infrakt proxy reload <server_name>
```

**Examples:**

```bash
infrakt proxy reload prod-1
```

Use this after manually editing the Caddyfile on the server to apply the changes. Note that infrakt manages the Caddyfile automatically — manual edits will be overwritten by the next `infrakt proxy add`, `proxy remove`, or `app deploy` that touches the proxy.

---

## Common Patterns

### Deploy a new app from scratch

```bash
# 1. Add and provision a server (one-time)
infrakt server add --name prod-1 --host 1.2.3.4 --key ~/.ssh/id_ed25519
infrakt server provision prod-1

# 2. Create a database
infrakt db create --server prod-1 --name appdb --type postgres
# Save the connection string output

# 3. Create the app
infrakt app create \
  --server prod-1 \
  --name myapp \
  --git https://github.com/you/myapp \
  --domain myapp.example.com \
  --port 3000

# 4. Set environment variables
infrakt env set myapp \
  DATABASE_URL=postgresql://appdb:<password>@localhost:5432/appdb \
  SECRET_KEY=$(openssl rand -hex 32) \
  NODE_ENV=production

# 5. Deploy
infrakt app deploy myapp
```

### Update environment variables without redeploying

```bash
infrakt env set myapp FEATURE_FLAG=true
infrakt env push myapp   # pushes .env and restarts containers
```

### Roll out a new version

```bash
infrakt app deploy myapp   # git pull + rebuild + restart
```

### Check what is running

```bash
infrakt server list
infrakt app list
infrakt db list
infrakt proxy domains prod-1
infrakt server status prod-1
```
