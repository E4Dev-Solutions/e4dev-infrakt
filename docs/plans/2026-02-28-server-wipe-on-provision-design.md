# Server Wipe-on-Provision Design

**Date:** 2026-02-28

## Problem

When provisioning an additional server, the user wants a clean slate — all existing Docker containers, images, volumes, and `/opt/infrakt/` data should be wiped before provisioning. Currently, provisioning only installs software and is additive; there's no cleanup step.

The server hosting infrakT itself must be protected from wipe to avoid self-destruction.

## Design

### 1. Server Model — `is_infrakt_host` Flag

Add `is_infrakt_host: Boolean, default=False` column to the `Server` model. This flag identifies the server running infrakT and prevents it from being wiped.

### 2. `setup-vps.sh` — Set Flag After Registration

After the existing `POST /api/servers` call (line 349), add a `PATCH /api/servers/{name}` call to set `is_infrakt_host=True`.

### 3. API — `ServerUpdate` Schema

Add `is_infrakt_host: bool | None` to the `ServerUpdate` Pydantic model. The `PATCH /api/servers/{name}` endpoint already handles partial updates — this field piggybacks on that.

### 4. Provision Workflow — Wipe-Then-Provision

Both CLI (`infrakt server provision <name>`) and API (`POST /api/servers/{name}/provision`) follow this logic:

```
if server.is_infrakt_host:
    → provision normally (no wipe)
else:
    → wipe, then provision
```

**Wipe steps (via SSH):**

1. `docker stop $(docker ps -aq)` — stop all containers
2. `docker system prune -af --volumes` — remove all images, containers, volumes, networks
3. `rm -rf /opt/infrakt/` — delete entire infrakt directory

**Local DB cleanup:**

4. Delete all `App` records for that server (cascade deletes deployments, dependencies)
5. Delete all encrypted env files for those apps from `~/.infrakt/envs/`

**Then proceed with normal provision steps** (Docker install, Traefik, UFW, fail2ban, directory creation, etc.)

### 5. CLI Confirmation

Before wiping, require type-to-confirm:

```
All data on 'prod-2' will be destroyed. Type the server name to confirm: _
```

### 6. Dashboard — Confirmation Modal

The Provision button on non-infrakt-host servers shows a confirmation modal:

> **Warning: This will wipe all data on prod-2**
>
> All Docker containers, images, volumes, and app data will be permanently deleted before reprovisioning.
>
> Type "prod-2" to confirm: [________]
>
> [Cancel] [Wipe & Provision]

For the infrakT host server, the Provision button works as before (no wipe warning).

### 7. Provisioner Module Changes

`cli/core/provisioner.py` gets a new `wipe_server(ssh: SSHClient)` function containing the three SSH commands. The existing `provision_server()` function calls `wipe_server()` first when `is_infrakt_host` is `False`.

### Files Changed

| File | Change |
|------|--------|
| `cli/models/server.py` | Add `is_infrakt_host` column |
| `cli/core/provisioner.py` | Add `wipe_server()`, call it in provision flow |
| `cli/commands/server.py` | Add type-to-confirm before provision wipe |
| `api/schemas.py` | Add `is_infrakt_host` to `ServerUpdate` |
| `api/routes/servers.py` | Pass `is_infrakt_host` context to provision endpoint |
| `scripts/setup-vps.sh` | Add PATCH call to set `is_infrakt_host=True` |
| `frontend/src/pages/ServerDetail.tsx` | Add wipe confirmation modal to Provision button |
| `tests/` | Unit tests for wipe logic, flag protection |
| `frontend/e2e/` | E2E tests for provision confirmation modal |
