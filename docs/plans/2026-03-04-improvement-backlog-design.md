# infrakt Improvement Backlog — Design Document

Date: 2026-03-04
Origin: Dokploy comparison analysis

## Overview

11 items across 3 phases: bug fixes, deployment pipeline improvements, and UX/integration features. Ordered by dependency and risk.

---

## Phase 1: Bug Fixes

### 1. Health Check Gate

**Problem:** Rolling deploy health gate in `deployer.py:229-248` calls `reconcile_app_status()` which only checks Docker container state (`docker compose ps`). It never calls the actual HTTP health check URL even though `health_check_url` is passed into `deploy_app()`.

**Fix:** Replace `reconcile_app_status(ssh, app_name)` with `check_app_health(ssh, port, health_check_url)` from `cli/core/health.py`. Gate on `result["healthy"] == True`.

**Files:** `cli/core/deployer.py`

### 2. Postgres Restore Safety

**Problem:** Backup uses plain `pg_dump` (no `-Fc`), restore uses `gunzip | psql`. Restoring over existing data produces duplicate table errors that `psql` silently ignores (exits 0), leaving the DB in an inconsistent state.

**Fix:**
- Backup: change to `pg_dump -Fc` (custom format), use `.dump` extension instead of `.sql.gz`
- Restore: use `pg_restore --clean --if-exists --no-owner` instead of `gunzip | psql`
- Backward compat: if backup file ends in `.sql.gz` (old format), fall back to `gunzip | psql`
- Update `generate_backup_script()` to match

**Files:** `cli/core/backup.py`

### 3. Deploy Key Scope Enforcement

**Problem:** `validate_deploy_key()` returns metadata including `scopes: ["deploy"]` but the caller in `api/routes/deploy.py:57` never checks it. Any valid key works for any operation.

**Fix:** Change `if dk is not None:` to `if dk is not None and "deploy" in dk.get("scopes", []):` in `_require_api_or_deploy_key()`.

**Files:** `api/routes/deploy.py`

### 4. Double-Wipe Bug

**Problem:** In `api/routes/servers.py` `_do_provision()`, the `if not is_infrakt_host:` block (wipe + app record cleanup) is duplicated verbatim at lines 193-222. `wipe_server()` runs twice.

**Fix:** Delete the second copy of the block.

**Files:** `api/routes/servers.py`

---

## Phase 2: Deployment Pipeline

### 5. Near-Zero-Downtime Deploys

**Problem:** `docker compose up -d --build` stops the old container, builds the new image, then starts the new container. Downtime = entire build duration.

**Fix:** Split into two commands:
```bash
docker compose build                  # build while old container still serves
docker compose up -d --remove-orphans # instant swap (image ready)
```

Applies to 2 locations in `deploy_app()`:
- Git repo with own compose (line 162)
- Git repo with generated compose (line 182)

Image-based (`--pull always`) and compose-override deploys are unaffected.

**Files:** `cli/core/deployer.py`

### 6. Nixpacks Builder

**Goal:** Auto-detect language and build without a Dockerfile. Most repos don't have one.

**Provisioner:** Add installation step: `curl -sSL https://nixpacks.com/install.sh | bash`

**App model:** Add `build_type` column: `"auto"` (default), `"dockerfile"`, `"nixpacks"`.
- `"auto"`: use Dockerfile if present in repo, else Nixpacks
- `"dockerfile"`: always use Dockerfile (error if missing)
- `"nixpacks"`: always use Nixpacks

**Deployer flow for Nixpacks:**
```bash
nixpacks build ./repo --name infrakt-{app_name}   # produces Docker image
```
Then the generated compose uses `image: infrakt-{app_name}` instead of `build: ./repo`. The `docker compose up -d` swaps the container using the pre-built image (no `--build`).

**Integration with split build/swap (item 5):**
- Dockerfile path: `docker compose build` then `docker compose up -d`
- Nixpacks path: `nixpacks build` then `docker compose up -d` (compose references image)

**API/Frontend:** Add `build_type` field to `AppCreate`/`AppUpdate` schemas. Show in app settings.

**Files:** `cli/core/provisioner.py`, `cli/core/deployer.py`, `cli/models/app.py`, `api/schemas.py`, `api/routes/apps.py`, `cli/core/compose_renderer.py`, `cli/templates/app-compose.yml.j2`, frontend app settings

### 7. Image-Based Rollbacks

**Problem:** Currently only git apps support rollback via `git reset --hard <commit>` + full rebuild. Image and template apps have no rollback. Even git rollbacks are slow (rebuild required).

**Fix:** After every successful build, tag the image:
```bash
docker tag infrakt-{app_name} infrakt-{app_name}:v{deployment_id}
```

Store `image_tag` in the `Deployment` model (new column).

**Rollback flow:**
1. Look up target deployment's `image_tag`
2. Generate compose with `image: infrakt-{app_name}:v{N}`
3. `docker compose up -d` — instant swap, no rebuild

**Works for:** git builds (Dockerfile and Nixpacks), image-based deploys. Template/compose-override apps cannot rollback (they don't build a single image).

**Cleanup:** Keep last 5 tagged images per app. On deploy, prune older tags via `docker rmi`.

**Files:** `cli/core/deployer.py`, `cli/models/deployment.py`, `api/routes/apps.py`, frontend rollback UI

---

## Phase 3: UX & Integration

### 8. Store DB Passwords Encrypted

**Problem:** Database passwords are printed once at creation time and never stored. Users lose them.

**Fix:** Add `db_password_encrypted` column to App model (nullable String). Encrypt with Fernet on DB creation. Add API endpoint `GET /api/databases/{name}/credentials` to retrieve decrypted connection string. Frontend: "Show credentials" button on database detail page.

**Files:** `cli/models/app.py`, `cli/commands/db.py`, `api/routes/databases.py`, `api/schemas.py`, frontend database detail

### 9. GitHub Webhook Cleanup

**Problem:** `create_repo_webhook()` IS called on first deploy (found in `api/routes/apps.py:467-494`), but the returned `hook_id` is discarded. When an app is destroyed, the GitHub webhook is orphaned.

**Fix:** Add `github_hook_id` column to App. Store the hook ID on webhook creation. On `destroy_app`, call `delete_repo_webhook()` to clean up the GitHub side.

**Files:** `cli/models/app.py`, `api/routes/apps.py`

### 10. Bulk .env Import

**Fix:** New endpoint `POST /api/apps/{name}/env/import` with body `{"content": "KEY=val\nKEY2=val2"}`. Parse `.env` format (skip comments/blanks, handle `"quoted values"`, `KEY=` for empty values). Encrypt each value, store. Frontend: "Import .env" button → textarea modal.

**Files:** `api/routes/env.py`, `api/schemas.py`, frontend env tab

### 11. Slack/Discord Notifications

**Fix:** Add `channel_type` column to Webhook model: `"custom"` (default), `"slack"`, `"discord"`.

Dispatch in `fire_webhooks()`:
- `custom`: current HMAC-signed JSON POST
- `slack`: POST `{"text": "[infrakt] Deploy of {app} on {server}: success"}` to webhook URL
- `discord`: POST `{"content": "[infrakt] Deploy of {app} on {server}: success"}` to webhook URL

**Files:** `cli/models/webhook.py`, `cli/core/webhook_sender.py`, `api/schemas.py`, `api/routes/webhooks.py`, frontend webhook form

---

## Migration Notes

- Phase 2 items 6 and 7 add new columns (`build_type`, `image_tag`, `db_password_encrypted`, `github_hook_id`, `channel_type`). All are nullable with defaults, so Alembic migrations are backward-compatible.
- Postgres backup format change (item 2) is backward-compatible: old `.sql.gz` files restore via legacy path, new `.dump` files use `pg_restore`.
- Nixpacks installation (item 6) only affects newly provisioned servers. Existing servers need manual install or re-provision.
