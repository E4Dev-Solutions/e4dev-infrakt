# S3 Backup Storage — Design

## Goal

Allow database backups to be automatically uploaded to S3-compatible storage (AWS S3, DigitalOcean Spaces, Backblaze B2, etc.) directly from the remote server, with global configuration managed through the Settings page.

## Architecture

**Approach:** Server-side S3 upload via `awscli`. After a backup file is created on the remote server, the server uploads directly to S3 — no data flows through the developer's machine. S3 credentials are stored encrypted in a local SQLite table and pushed to the server as temporary files during upload/download operations.

**S3 is transparent.** If configured, every backup (manual or scheduled) auto-uploads to S3. If not configured, backups remain local-only on the server as they do today.

## S3 Configuration Storage

New `S3Config` SQLAlchemy model in `cli/models/s3_config.py`:
- `id`, `endpoint_url`, `bucket`, `region`, `access_key`, `secret_key_encrypted`, `prefix`, `created_at`, `updated_at`
- Only one row — global configuration
- Secret key encrypted with Fernet (same as env vars and GitHub token)

New API endpoints in `api/routes/settings.py`:
- `GET /api/settings/s3` — returns current S3 config (secret key masked)
- `PUT /api/settings/s3` — save/update S3 config
- `DELETE /api/settings/s3` — remove S3 config
- `POST /api/settings/s3/test` — test connectivity by listing the bucket

## Server-Side Upload/Download

**awscli installation:** Add `pip3 install awscli` to `PROVISION_STEPS` in `provisioner.py`.

**Upload flow** (`upload_backup_to_s3()` in `cli/core/backup.py`):
1. Write temporary AWS credentials file on the server via SSH
2. Run `aws s3 cp <local_path> s3://<bucket>/<prefix>/<db_name>/<filename> --endpoint-url <endpoint>`
3. Clean up the temp credentials file

**Download flow** (`download_backup_from_s3()` in `cli/core/backup.py`):
1. Same temp credentials approach
2. Run `aws s3 cp s3://<bucket>/<prefix>/<filename> /opt/infrakt/backups/<filename> --endpoint-url <endpoint>`
3. Existing `restore_database()` handles the rest

**Scheduled backups:** `generate_backup_script()` includes the S3 upload command after the local backup when S3 is configured, so every cron backup auto-uploads.

**List S3 backups:** `list_s3_backups()` runs `aws s3 ls s3://<bucket>/<prefix>/<db_name>/` to list remote backups.

## API Changes

- `POST /api/databases/{name}/backup` — add optional `upload_to_s3: bool = True` param (defaults to true if S3 is configured)
- `GET /api/databases/{name}/backups` — merge local and S3 backup lists, mark each with `location: "local" | "s3" | "both"`
- `POST /api/databases/{name}/restore` — accept S3 filenames; downloads from S3 first if not present locally

## Frontend

**Settings page — S3 Backup Storage section** (below SSH Keys):
- Endpoint URL, bucket, region, access key, secret key (password field), path prefix
- "Test Connection" button — success/error toast
- Save and Delete buttons

**Database Detail — Backups tab:**
- Backup list shows cloud icon for S3 backups
- "Create Backup" auto-uploads to S3 if configured
- Restore from S3: downloads first, then restores
- "S3 only" indicator for backups cleaned up locally but still in S3

## Testing

- Backend unit tests: S3Config CRUD, upload/download functions (mock SSH), backup script generation with S3 commands
- E2E tests: S3 settings form (save, test, delete), S3 indicator on backup list
