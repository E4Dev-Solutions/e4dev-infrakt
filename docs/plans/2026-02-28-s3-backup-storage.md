# S3 Backup Storage Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upload database backups to S3-compatible storage directly from the remote server, with global configuration managed through the Settings page.

**Architecture:** New `S3Config` model stores encrypted credentials in SQLite. Server-side `awscli` handles uploads/downloads. Existing backup flow is extended: after creating a local backup, the server pushes it to S3. Scheduled cron scripts include the S3 upload step. The frontend Settings page gets an S3 config section, and the Database Detail backups tab shows S3 status per backup.

**Tech Stack:** Python (SQLAlchemy, FastAPI, Fernet encryption), awscli (installed on server via provisioning), React (TanStack Query), Playwright E2E tests.

---

### Task 1: S3Config Model

**Files:**
- Create: `cli/models/s3_config.py`
- Modify: `cli/models/__init__.py`
- Test: `tests/unit/test_s3_config_model.py`

**Step 1: Write the failing test**

Create `tests/unit/test_s3_config_model.py`:

```python
"""Tests for S3Config model."""

from cli.core.database import get_session, init_db
from cli.models.s3_config import S3Config


class TestS3ConfigModel:
    def test_create_s3_config(self, isolated_config):
        init_db()
        with get_session() as session:
            config = S3Config(
                endpoint_url="https://s3.amazonaws.com",
                bucket="my-backups",
                region="us-east-1",
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key_encrypted="encrypted-secret",
                prefix="infrakt/",
            )
            session.add(config)
            session.flush()
            assert config.id is not None

    def test_read_s3_config(self, isolated_config):
        init_db()
        with get_session() as session:
            config = S3Config(
                endpoint_url="https://nyc3.digitaloceanspaces.com",
                bucket="backups",
                region="nyc3",
                access_key="DO_KEY",
                secret_key_encrypted="encrypted",
                prefix="",
            )
            session.add(config)

        with get_session() as session:
            found = session.query(S3Config).first()
            assert found is not None
            assert found.endpoint_url == "https://nyc3.digitaloceanspaces.com"
            assert found.bucket == "backups"

    def test_prefix_defaults_to_empty(self, isolated_config):
        init_db()
        with get_session() as session:
            config = S3Config(
                endpoint_url="https://s3.amazonaws.com",
                bucket="b",
                region="us-east-1",
                access_key="k",
                secret_key_encrypted="s",
            )
            session.add(config)
            session.flush()
            assert config.prefix == ""
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_s3_config_model.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.models.s3_config'`

**Step 3: Write minimal implementation**

Create `cli/models/s3_config.py`:

```python
from __future__ import annotations

from datetime import datetime

from sqlalchemy import String, func
from sqlalchemy.orm import Mapped, mapped_column

from cli.core.database import Base


class S3Config(Base):
    __tablename__ = "s3_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    endpoint_url: Mapped[str] = mapped_column(String(500), nullable=False)
    bucket: Mapped[str] = mapped_column(String(200), nullable=False)
    region: Mapped[str] = mapped_column(String(50), nullable=False)
    access_key: Mapped[str] = mapped_column(String(200), nullable=False)
    secret_key_encrypted: Mapped[str] = mapped_column(String(500), nullable=False)
    prefix: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(default=func.now())
    updated_at: Mapped[datetime] = mapped_column(default=func.now(), onupdate=func.now())
```

Update `cli/models/__init__.py` — add the import and export:

```python
from cli.models.s3_config import S3Config
```

Add `"S3Config"` to the `__all__` list.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_s3_config_model.py -v`
Expected: PASS (3 tests)

**Step 5: Commit**

```bash
git add cli/models/s3_config.py cli/models/__init__.py tests/unit/test_s3_config_model.py
git commit -m "feat: add S3Config model for backup storage credentials"
```

---

### Task 2: S3 Settings API Endpoints

**Files:**
- Create: `api/routes/settings.py`
- Modify: `api/main.py` (register router)
- Modify: `api/schemas.py` (add S3 schemas)
- Test: `tests/unit/test_api_s3_settings.py`

**Step 1: Write the failing test**

Create `tests/unit/test_api_s3_settings.py`:

```python
"""Tests for S3 settings API endpoints."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)
HEADERS = {"X-API-Key": "test-key"}


@pytest.fixture(autouse=True)
def _auth(isolated_config):
    with patch("api.auth._load_api_key", return_value="test-key"):
        yield


class TestGetS3Config:
    def test_returns_empty_when_not_configured(self):
        resp = client.get("/api/settings/s3", headers=HEADERS)
        assert resp.status_code == 200
        assert resp.json() == {"configured": False}

    def test_returns_config_with_masked_secret(self):
        # First save a config
        client.put(
            "/api/settings/s3",
            headers=HEADERS,
            json={
                "endpoint_url": "https://s3.amazonaws.com",
                "bucket": "my-backups",
                "region": "us-east-1",
                "access_key": "AKIAIOSFODNN7EXAMPLE",
                "secret_key": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
                "prefix": "infrakt/",
            },
        )
        resp = client.get("/api/settings/s3", headers=HEADERS)
        assert resp.status_code == 200
        data = resp.json()
        assert data["configured"] is True
        assert data["endpoint_url"] == "https://s3.amazonaws.com"
        assert data["bucket"] == "my-backups"
        assert data["access_key"] == "AKIAIOSFODNN7EXAMPLE"
        assert "secret_key" not in data  # secret is never returned


class TestPutS3Config:
    def test_saves_new_config(self):
        resp = client.put(
            "/api/settings/s3",
            headers=HEADERS,
            json={
                "endpoint_url": "https://nyc3.digitaloceanspaces.com",
                "bucket": "backups",
                "region": "nyc3",
                "access_key": "DO_KEY",
                "secret_key": "DO_SECRET",
                "prefix": "",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["message"] == "S3 configuration saved"

    def test_updates_existing_config(self):
        client.put(
            "/api/settings/s3",
            headers=HEADERS,
            json={
                "endpoint_url": "https://s3.amazonaws.com",
                "bucket": "old-bucket",
                "region": "us-east-1",
                "access_key": "OLD_KEY",
                "secret_key": "OLD_SECRET",
                "prefix": "",
            },
        )
        resp = client.put(
            "/api/settings/s3",
            headers=HEADERS,
            json={
                "endpoint_url": "https://s3.amazonaws.com",
                "bucket": "new-bucket",
                "region": "us-west-2",
                "access_key": "NEW_KEY",
                "secret_key": "NEW_SECRET",
                "prefix": "prod/",
            },
        )
        assert resp.status_code == 200
        get_resp = client.get("/api/settings/s3", headers=HEADERS)
        assert get_resp.json()["bucket"] == "new-bucket"
        assert get_resp.json()["region"] == "us-west-2"


class TestDeleteS3Config:
    def test_deletes_existing_config(self):
        client.put(
            "/api/settings/s3",
            headers=HEADERS,
            json={
                "endpoint_url": "https://s3.amazonaws.com",
                "bucket": "b",
                "region": "r",
                "access_key": "k",
                "secret_key": "s",
                "prefix": "",
            },
        )
        resp = client.delete("/api/settings/s3", headers=HEADERS)
        assert resp.status_code == 200
        get_resp = client.get("/api/settings/s3", headers=HEADERS)
        assert get_resp.json()["configured"] is False

    def test_delete_returns_200_even_when_not_configured(self):
        resp = client.delete("/api/settings/s3", headers=HEADERS)
        assert resp.status_code == 200
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_api_s3_settings.py -v`
Expected: FAIL — `404 Not Found` (routes don't exist yet)

**Step 3: Write minimal implementation**

Add to `api/schemas.py`:

```python
class S3ConfigSave(BaseModel):
    endpoint_url: str = Field(..., min_length=1, max_length=500)
    bucket: str = Field(..., min_length=1, max_length=200)
    region: str = Field(..., max_length=50)
    access_key: str = Field(..., min_length=1, max_length=200)
    secret_key: str = Field(..., min_length=1, max_length=500)
    prefix: str = Field(default="", max_length=200)
```

Create `api/routes/settings.py`:

```python
"""Platform settings API routes (S3 backup storage, etc.)."""

from fastapi import APIRouter

from api.schemas import S3ConfigSave
from cli.core.crypto import decrypt, encrypt
from cli.core.database import get_session, init_db
from cli.models.s3_config import S3Config

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/s3")
def get_s3_config() -> dict:
    """Return the current S3 backup configuration (secret key masked)."""
    init_db()
    with get_session() as session:
        cfg = session.query(S3Config).first()
        if not cfg:
            return {"configured": False}
        return {
            "configured": True,
            "endpoint_url": cfg.endpoint_url,
            "bucket": cfg.bucket,
            "region": cfg.region,
            "access_key": cfg.access_key,
            "prefix": cfg.prefix,
        }


@router.put("/s3")
def save_s3_config(body: S3ConfigSave) -> dict[str, str]:
    """Save or update S3 backup configuration."""
    init_db()
    with get_session() as session:
        cfg = session.query(S3Config).first()
        if cfg:
            cfg.endpoint_url = body.endpoint_url
            cfg.bucket = body.bucket
            cfg.region = body.region
            cfg.access_key = body.access_key
            cfg.secret_key_encrypted = encrypt(body.secret_key)
            cfg.prefix = body.prefix
        else:
            cfg = S3Config(
                endpoint_url=body.endpoint_url,
                bucket=body.bucket,
                region=body.region,
                access_key=body.access_key,
                secret_key_encrypted=encrypt(body.secret_key),
                prefix=body.prefix,
            )
            session.add(cfg)
    return {"message": "S3 configuration saved"}


@router.delete("/s3")
def delete_s3_config() -> dict[str, str]:
    """Remove S3 backup configuration."""
    init_db()
    with get_session() as session:
        cfg = session.query(S3Config).first()
        if cfg:
            session.delete(cfg)
    return {"message": "S3 configuration removed"}
```

Register the router in `api/main.py` — add `from api.routes.settings import router as settings_router` and `app.include_router(settings_router, prefix="/api")` alongside the other router registrations.

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_api_s3_settings.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add api/routes/settings.py api/schemas.py api/main.py tests/unit/test_api_s3_settings.py
git commit -m "feat: add S3 settings API endpoints (GET/PUT/DELETE)"
```

---

### Task 3: S3 Upload/Download Functions

**Files:**
- Modify: `cli/core/backup.py` (add `upload_backup_to_s3`, `download_backup_from_s3`, `list_s3_backups`)
- Test: `tests/unit/test_s3_backup.py`

**Step 1: Write the failing test**

Create `tests/unit/test_s3_backup.py`:

```python
"""Tests for S3 backup upload/download functions."""

from unittest.mock import MagicMock

from cli.core.backup import download_backup_from_s3, list_s3_backups, upload_backup_to_s3


class TestUploadBackupToS3:
    def test_uploads_file_to_s3(self):
        ssh = MagicMock()
        ssh.run_checked.return_value = ""
        ssh.run.return_value = ("", "", 0)
        upload_backup_to_s3(
            ssh,
            local_path="/opt/infrakt/backups/mydb_20260228_020000.sql.gz",
            s3_endpoint="https://s3.amazonaws.com",
            bucket="my-backups",
            region="us-east-1",
            access_key="AKID",
            secret_key="SECRET",
            prefix="infrakt/",
            db_name="mydb",
        )
        calls = [str(c) for c in ssh.run_checked.call_args_list]
        assert any("aws s3 cp" in c for c in calls)
        assert any("my-backups" in c for c in calls)

    def test_cleans_up_credentials_file(self):
        ssh = MagicMock()
        ssh.run_checked.return_value = ""
        ssh.run.return_value = ("", "", 0)
        upload_backup_to_s3(
            ssh,
            local_path="/opt/infrakt/backups/test.sql.gz",
            s3_endpoint="https://s3.amazonaws.com",
            bucket="b",
            region="r",
            access_key="k",
            secret_key="s",
            prefix="",
            db_name="test",
        )
        calls = [str(c) for c in ssh.run.call_args_list]
        assert any("rm -f" in c for c in calls)


class TestDownloadBackupFromS3:
    def test_downloads_file_from_s3(self):
        ssh = MagicMock()
        ssh.run_checked.return_value = ""
        ssh.run.return_value = ("", "", 0)
        result = download_backup_from_s3(
            ssh,
            filename="mydb_20260228_020000.sql.gz",
            s3_endpoint="https://s3.amazonaws.com",
            bucket="my-backups",
            region="us-east-1",
            access_key="AKID",
            secret_key="SECRET",
            prefix="infrakt/",
            db_name="mydb",
        )
        assert result == "/opt/infrakt/backups/mydb_20260228_020000.sql.gz"
        calls = [str(c) for c in ssh.run_checked.call_args_list]
        assert any("aws s3 cp" in c for c in calls)


class TestListS3Backups:
    def test_parses_s3_ls_output(self):
        ssh = MagicMock()
        ssh.run_checked.return_value = ""
        ssh.run.return_value = (
            "2026-02-28 02:00:00    2516582 mydb_20260228_020000.sql.gz\n"
            "2026-02-27 02:00:00    2202009 mydb_20260227_020000.sql.gz\n",
            "",
            0,
        )
        results = list_s3_backups(
            ssh,
            s3_endpoint="https://s3.amazonaws.com",
            bucket="b",
            region="r",
            access_key="k",
            secret_key="s",
            prefix="infrakt/",
            db_name="mydb",
        )
        assert len(results) == 2
        assert results[0]["filename"] == "mydb_20260228_020000.sql.gz"
        assert results[0]["size_bytes"] == 2516582

    def test_returns_empty_for_no_files(self):
        ssh = MagicMock()
        ssh.run_checked.return_value = ""
        ssh.run.return_value = ("", "", 1)
        results = list_s3_backups(
            ssh,
            s3_endpoint="https://s3.amazonaws.com",
            bucket="b",
            region="r",
            access_key="k",
            secret_key="s",
            prefix="",
            db_name="mydb",
        )
        assert results == []
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_s3_backup.py -v`
Expected: FAIL — `ImportError: cannot import name 'upload_backup_to_s3'`

**Step 3: Write minimal implementation**

Add to `cli/core/backup.py` (at the end of the file):

```python
# ---------------------------------------------------------------------------
# S3 backup operations
# ---------------------------------------------------------------------------


def _write_aws_credentials(
    ssh: SSHClient,
    access_key: str,
    secret_key: str,
    region: str,
) -> str:
    """Write a temporary AWS credentials/config file pair and return the creds path."""
    creds_path = "/tmp/.infrakt-aws-credentials"
    config_path = "/tmp/.infrakt-aws-config"
    creds_content = f"[default]\naws_access_key_id = {access_key}\naws_secret_access_key = {secret_key}\n"
    config_content = f"[default]\nregion = {region}\n"
    ssh.upload_string(creds_content, creds_path)
    ssh.upload_string(config_content, config_path)
    ssh.run(f"chmod 600 {creds_path} {config_path}")
    return creds_path


def _cleanup_aws_credentials(ssh: SSHClient) -> None:
    """Remove temporary AWS credential files."""
    ssh.run("rm -f /tmp/.infrakt-aws-credentials /tmp/.infrakt-aws-config")


def _aws_env_prefix() -> str:
    """Return the environment variable prefix for aws CLI with temp credentials."""
    return (
        "AWS_SHARED_CREDENTIALS_FILE=/tmp/.infrakt-aws-credentials "
        "AWS_CONFIG_FILE=/tmp/.infrakt-aws-config "
    )


def upload_backup_to_s3(
    ssh: SSHClient,
    local_path: str,
    s3_endpoint: str,
    bucket: str,
    region: str,
    access_key: str,
    secret_key: str,
    prefix: str,
    db_name: str,
) -> None:
    """Upload a backup file from the remote server to S3."""
    _write_aws_credentials(ssh, access_key, secret_key, region)
    try:
        s3_key = f"{prefix}{db_name}/{local_path.rsplit('/', 1)[-1]}" if prefix else f"{db_name}/{local_path.rsplit('/', 1)[-1]}"
        q_local = shlex.quote(local_path)
        q_s3 = shlex.quote(f"s3://{bucket}/{s3_key}")
        q_endpoint = shlex.quote(s3_endpoint)
        cmd = f"{_aws_env_prefix()}aws s3 cp {q_local} {q_s3} --endpoint-url {q_endpoint}"
        ssh.run_checked(cmd, timeout=300)
    finally:
        _cleanup_aws_credentials(ssh)


def download_backup_from_s3(
    ssh: SSHClient,
    filename: str,
    s3_endpoint: str,
    bucket: str,
    region: str,
    access_key: str,
    secret_key: str,
    prefix: str,
    db_name: str,
    backup_dir: str = "/opt/infrakt/backups",
) -> str:
    """Download a backup file from S3 to the remote server. Returns the local path."""
    _write_aws_credentials(ssh, access_key, secret_key, region)
    try:
        s3_key = f"{prefix}{db_name}/{filename}" if prefix else f"{db_name}/{filename}"
        local_path = f"{backup_dir}/{filename}"
        q_s3 = shlex.quote(f"s3://{bucket}/{s3_key}")
        q_local = shlex.quote(local_path)
        q_endpoint = shlex.quote(s3_endpoint)
        ssh.run_checked(f"mkdir -p {shlex.quote(backup_dir)}")
        cmd = f"{_aws_env_prefix()}aws s3 cp {q_s3} {q_local} --endpoint-url {q_endpoint}"
        ssh.run_checked(cmd, timeout=300)
    finally:
        _cleanup_aws_credentials(ssh)
    return local_path


def list_s3_backups(
    ssh: SSHClient,
    s3_endpoint: str,
    bucket: str,
    region: str,
    access_key: str,
    secret_key: str,
    prefix: str,
    db_name: str,
) -> list[dict[str, str | int]]:
    """List backup files in S3 for a given database. Returns list of dicts."""
    _write_aws_credentials(ssh, access_key, secret_key, region)
    try:
        s3_prefix = f"{prefix}{db_name}/" if prefix else f"{db_name}/"
        q_s3 = shlex.quote(f"s3://{bucket}/{s3_prefix}")
        q_endpoint = shlex.quote(s3_endpoint)
        cmd = f"{_aws_env_prefix()}aws s3 ls {q_s3} --endpoint-url {q_endpoint}"
        stdout, _, rc = ssh.run(cmd, timeout=30)
    finally:
        _cleanup_aws_credentials(ssh)

    if rc != 0 or not stdout.strip():
        return []

    results: list[dict[str, str | int]] = []
    for line in stdout.strip().splitlines():
        # Format: "2026-02-28 02:00:00    2516582 filename.sql.gz"
        parts = line.split()
        if len(parts) < 4:
            continue
        try:
            date_str = f"{parts[0]} {parts[1]}"
            size_bytes = int(parts[2])
            fname = parts[3]
        except (ValueError, IndexError):
            continue
        results.append({
            "filename": fname,
            "size": _human_size(size_bytes),
            "size_bytes": size_bytes,
            "modified": date_str,
        })
    return results
```

**Step 4: Run test to verify it passes**

Run: `python3 -m pytest tests/unit/test_s3_backup.py -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add cli/core/backup.py tests/unit/test_s3_backup.py
git commit -m "feat: add S3 upload/download/list functions for backups"
```

---

### Task 4: awscli Provisioning Step

**Files:**
- Modify: `cli/core/provisioner.py` (add awscli install step to `PROVISION_STEPS`)
- Modify: `tests/unit/test_provisioner_wipe.py` (no changes needed, wipe doesn't touch awscli)

**Step 1: Add awscli install step**

In `cli/core/provisioner.py`, add this step to `PROVISION_STEPS` after the "Installing Docker" step:

```python
(
    "Installing awscli",
    "pip3 install -q awscli 2>/dev/null || apt-get install -y -qq awscli 2>/dev/null || true",
),
```

**Step 2: Run existing provisioner tests**

Run: `python3 -m pytest tests/unit/test_provisioner_wipe.py tests/unit/test_provision_wipe_integration.py -v`
Expected: PASS

**Step 3: Commit**

```bash
git add cli/core/provisioner.py
git commit -m "feat: install awscli during server provisioning"
```

---

### Task 5: Integrate S3 Into Backup API Endpoints

**Files:**
- Modify: `api/routes/databases.py` (enhance backup, list, restore endpoints)
- Modify: `api/schemas.py` (add `location` field to `BackupFileOut`)
- Test: `tests/unit/test_api_databases.py` (add S3 integration tests)

**Step 1: Update `BackupFileOut` schema**

In `api/schemas.py`, add a `location` field to `BackupFileOut`:

```python
class BackupFileOut(BaseModel):
    filename: str
    size: str
    size_bytes: int
    modified: str
    location: str = "local"  # "local", "s3", or "both"
```

**Step 2: Create helper to get S3 config**

Add a helper function at the top of `api/routes/databases.py`:

```python
def _get_s3_config() -> dict | None:
    """Return decrypted S3 config dict, or None if not configured."""
    from cli.core.crypto import decrypt
    from cli.models.s3_config import S3Config

    with get_session() as session:
        cfg = session.query(S3Config).first()
        if not cfg:
            return None
        return {
            "endpoint_url": cfg.endpoint_url,
            "bucket": cfg.bucket,
            "region": cfg.region,
            "access_key": cfg.access_key,
            "secret_key": decrypt(cfg.secret_key_encrypted),
            "prefix": cfg.prefix,
        }
```

**Step 3: Enhance backup endpoint**

In `backup_database_endpoint`, after `backup_database()` returns the remote path, check if S3 is configured and upload:

```python
# After: remote_path = backup_database(ssh, db_app)
# Add:
s3_cfg = _get_s3_config()
if s3_cfg:
    from cli.core.backup import upload_backup_to_s3
    upload_backup_to_s3(
        ssh,
        local_path=remote_path,
        s3_endpoint=s3_cfg["endpoint_url"],
        bucket=s3_cfg["bucket"],
        region=s3_cfg["region"],
        access_key=s3_cfg["access_key"],
        secret_key=s3_cfg["secret_key"],
        prefix=s3_cfg["prefix"],
        db_name=name,
    )
```

**Step 4: Enhance list backups endpoint**

In `list_database_backups`, after getting local backups, also list S3 backups and merge:

```python
s3_cfg = _get_s3_config()
s3_files: list[dict] = []
if s3_cfg:
    from cli.core.backup import list_s3_backups as _list_s3
    try:
        with ssh:
            s3_files = _list_s3(
                ssh,
                s3_endpoint=s3_cfg["endpoint_url"],
                bucket=s3_cfg["bucket"],
                region=s3_cfg["region"],
                access_key=s3_cfg["access_key"],
                secret_key=s3_cfg["secret_key"],
                prefix=s3_cfg["prefix"],
                db_name=name,
            )
    except Exception:
        pass

# Merge: mark location for each file
local_names = {b["filename"] for b in backups}
s3_names = {b["filename"] for b in s3_files}
results = []
for b in backups:
    loc = "both" if b["filename"] in s3_names else "local"
    results.append(BackupFileOut(**b, location=loc))
for b in s3_files:
    if b["filename"] not in local_names:
        results.append(BackupFileOut(**b, location="s3"))
return results
```

**Step 5: Enhance restore endpoint**

In `restore_database_endpoint`, before restoring, check if the file exists locally. If not, download from S3:

```python
# Before calling restore_database(), add:
with ssh:
    _, _, rc = ssh.run(f"test -f {shlex.quote(remote_path)}")
    if rc != 0:
        # File not local — try S3
        s3_cfg = _get_s3_config()
        if not s3_cfg:
            raise HTTPException(404, f"Backup file not found: {body.filename}")
        from cli.core.backup import download_backup_from_s3
        download_backup_from_s3(
            ssh,
            filename=body.filename,
            s3_endpoint=s3_cfg["endpoint_url"],
            bucket=s3_cfg["bucket"],
            region=s3_cfg["region"],
            access_key=s3_cfg["access_key"],
            secret_key=s3_cfg["secret_key"],
            prefix=s3_cfg["prefix"],
            db_name=name,
        )
```

**Step 6: Run tests**

Run: `python3 -m pytest tests/unit/test_api_databases.py -v`
Expected: PASS (existing tests still work, `location` defaults to `"local"`)

**Step 7: Commit**

```bash
git add api/routes/databases.py api/schemas.py
git commit -m "feat: integrate S3 upload/download into backup API endpoints"
```

---

### Task 6: Enhance Scheduled Backup Script With S3

**Files:**
- Modify: `cli/core/backup.py` (`generate_backup_script` — add S3 upload step)
- Modify: `api/routes/databases.py` (`schedule_backup_endpoint` — pass S3 config)
- Test: `tests/unit/test_backup_schedule.py` (add S3 test)

**Step 1: Write the failing test**

Add to `tests/unit/test_backup_schedule.py`:

```python
class TestGenerateBackupScriptWithS3:
    def test_includes_aws_s3_cp_when_s3_config_provided(self):
        app = _make_app("testdb", "db:postgres")
        script = generate_backup_script(
            app,
            s3_endpoint="https://s3.amazonaws.com",
            s3_bucket="my-backups",
            s3_region="us-east-1",
            s3_access_key="AKID",
            s3_secret_key="SECRET",
            s3_prefix="infrakt/",
        )
        assert "aws s3 cp" in script
        assert "my-backups" in script
        assert "AKID" not in script  # credentials via env vars, not inline

    def test_no_s3_when_config_not_provided(self):
        app = _make_app("testdb", "db:postgres")
        script = generate_backup_script(app)
        assert "aws s3 cp" not in script
```

**Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/unit/test_backup_schedule.py::TestGenerateBackupScriptWithS3 -v`
Expected: FAIL — `TypeError` (unexpected keyword arguments)

**Step 3: Update `generate_backup_script` signature**

Add optional S3 parameters to `generate_backup_script` in `cli/core/backup.py`:

```python
def generate_backup_script(
    db_app: App,
    backup_dir: str = "/opt/infrakt/backups",
    retention_days: int = 7,
    s3_endpoint: str | None = None,
    s3_bucket: str | None = None,
    s3_region: str | None = None,
    s3_access_key: str | None = None,
    s3_secret_key: str | None = None,
    s3_prefix: str = "",
) -> str:
```

After the retention cleanup lines, add:

```python
if s3_endpoint and s3_bucket and s3_access_key and s3_secret_key:
    s3_key = f"{s3_prefix}{name}/${{BACKUP_FILE}}" if s3_prefix else f"{name}/${{BACKUP_FILE}}"
    lines.extend([
        "",
        "# Upload to S3",
        f"export AWS_ACCESS_KEY_ID={shlex.quote(s3_access_key)}",
        f"export AWS_SECRET_ACCESS_KEY={shlex.quote(s3_secret_key)}",
        f"export AWS_DEFAULT_REGION={shlex.quote(s3_region or '')}",
        f"BACKUP_FILE={filename}",
        f"aws s3 cp \"$BACKUP_DIR/$BACKUP_FILE\" {shlex.quote(f's3://{s3_bucket}/{s3_key}')} "
        f"--endpoint-url {shlex.quote(s3_endpoint)} || true",
        "unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION",
    ])
```

Note: We need to capture the filename into a variable. Above the retention lines, add:

```python
lines.append(f"BACKUP_FILE={filename}")
```

And reference `$BACKUP_FILE` in the S3 cp command.

**Step 4: Update `install_backup_cron` / `schedule_backup_endpoint`**

In `api/routes/databases.py`, the `schedule_backup_endpoint` should pass S3 config to `install_backup_cron`. Update `install_backup_cron` to accept optional S3 kwargs and pass them to `generate_backup_script`.

**Step 5: Run tests**

Run: `python3 -m pytest tests/unit/test_backup_schedule.py -v`
Expected: PASS

**Step 6: Commit**

```bash
git add cli/core/backup.py api/routes/databases.py tests/unit/test_backup_schedule.py
git commit -m "feat: include S3 upload in scheduled backup scripts"
```

---

### Task 7: Frontend — S3 Config API Client + Hooks

**Files:**
- Modify: `frontend/src/api/client.ts` (add `s3Api` namespace)
- Modify: `frontend/src/hooks/useApi.ts` (add S3 hooks)

**Step 1: Add types and API client**

In `frontend/src/api/client.ts`, add the `S3Config` type and `s3Api` namespace:

```typescript
export interface S3Config {
  configured: boolean;
  endpoint_url?: string;
  bucket?: string;
  region?: string;
  access_key?: string;
  prefix?: string;
}

export interface S3ConfigSave {
  endpoint_url: string;
  bucket: string;
  region: string;
  access_key: string;
  secret_key: string;
  prefix: string;
}

export const s3Api = {
  get: (): Promise<S3Config> => get("/settings/s3"),
  save: (config: S3ConfigSave): Promise<{ message: string }> => put("/settings/s3", config),
  delete: (): Promise<{ message: string }> => del("/settings/s3"),
  test: (): Promise<{ message: string }> => post("/settings/s3/test"),
};
```

**Step 2: Add TanStack Query hooks**

In `frontend/src/hooks/useApi.ts`, add:

```typescript
export function useS3Config() {
  return useQuery({ queryKey: ["s3-config"], queryFn: s3Api.get });
}

export function useSaveS3Config() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: s3Api.save,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["s3-config"] }); },
  });
}

export function useDeleteS3Config() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: s3Api.delete,
    onSuccess: () => { void qc.invalidateQueries({ queryKey: ["s3-config"] }); },
  });
}
```

**Step 3: Update `BackupFile` type**

In the `BackupFile` interface in `client.ts`, add:

```typescript
location?: "local" | "s3" | "both";
```

**Step 4: Run type check**

Run: `cd frontend && npm run type-check`
Expected: PASS

**Step 5: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/hooks/useApi.ts
git commit -m "feat: add S3 config API client and TanStack Query hooks"
```

---

### Task 8: Frontend — S3 Settings Section

**Files:**
- Modify: `frontend/src/pages/Settings.tsx` (add S3 Backup Storage section)

**Step 1: Add S3 section to Settings page**

Import the new hooks at the top of `Settings.tsx`:

```typescript
import { useS3Config, useSaveS3Config, useDeleteS3Config } from "@/hooks/useApi";
import { Cloud } from "lucide-react";
```

Add state hooks for the S3 form:

```typescript
const { data: s3Config, isLoading: s3Loading } = useS3Config();
const saveS3 = useSaveS3Config();
const deleteS3 = useDeleteS3Config();

const [s3Endpoint, setS3Endpoint] = useState("");
const [s3Bucket, setS3Bucket] = useState("");
const [s3Region, setS3Region] = useState("");
const [s3AccessKey, setS3AccessKey] = useState("");
const [s3SecretKey, setS3SecretKey] = useState("");
const [s3Prefix, setS3Prefix] = useState("");
```

Add a `useEffect` to populate form fields when config loads:

```typescript
useEffect(() => {
  if (s3Config?.configured) {
    setS3Endpoint(s3Config.endpoint_url ?? "");
    setS3Bucket(s3Config.bucket ?? "");
    setS3Region(s3Config.region ?? "");
    setS3AccessKey(s3Config.access_key ?? "");
    setS3Prefix(s3Config.prefix ?? "");
  }
}, [s3Config]);
```

Add the section after the Webhooks section and before the closing `</div>`. Use the same card pattern as SSH Keys and Webhooks:

```tsx
{/* S3 Backup Storage section */}
<section aria-labelledby="s3-heading" className="mb-10">
  <div className="mb-4">
    <h2 id="s3-heading" className="text-base font-semibold text-zinc-100">
      S3 Backup Storage
    </h2>
    <p className="mt-1 text-sm text-zinc-400">
      Configure S3-compatible storage for off-server database backups. Works with AWS S3, DigitalOcean Spaces, Backblaze B2, and more.
    </p>
  </div>
  <form
    onSubmit={async (e) => {
      e.preventDefault();
      try {
        await saveS3.mutateAsync({
          endpoint_url: s3Endpoint,
          bucket: s3Bucket,
          region: s3Region,
          access_key: s3AccessKey,
          secret_key: s3SecretKey,
          prefix: s3Prefix,
        });
        toast.success("S3 configuration saved");
        setS3SecretKey("");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Failed to save S3 config");
      }
    }}
    className="rounded-xl border border-zinc-700 bg-zinc-800 p-5"
  >
    {/* Status badge */}
    {s3Config?.configured && (
      <div className="mb-4 inline-flex items-center gap-2 rounded-md bg-emerald-500/10 px-2.5 py-1 text-xs font-medium text-emerald-300 ring-1 ring-emerald-500/30">
        <Cloud size={12} /> Connected
      </div>
    )}

    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      <div className="sm:col-span-2">
        <label className="mb-1.5 block text-xs font-medium text-zinc-300">
          Endpoint URL <span className="text-red-400">*</span>
        </label>
        <input type="url" required value={s3Endpoint} onChange={(e) => setS3Endpoint(e.target.value)}
          placeholder="https://s3.amazonaws.com"
          className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none" />
      </div>
      <div>
        <label className="mb-1.5 block text-xs font-medium text-zinc-300">
          Bucket <span className="text-red-400">*</span>
        </label>
        <input type="text" required value={s3Bucket} onChange={(e) => setS3Bucket(e.target.value)}
          placeholder="my-backups"
          className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none" />
      </div>
      <div>
        <label className="mb-1.5 block text-xs font-medium text-zinc-300">Region</label>
        <input type="text" value={s3Region} onChange={(e) => setS3Region(e.target.value)}
          placeholder="us-east-1"
          className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none" />
      </div>
      <div>
        <label className="mb-1.5 block text-xs font-medium text-zinc-300">
          Access Key <span className="text-red-400">*</span>
        </label>
        <input type="text" required value={s3AccessKey} onChange={(e) => setS3AccessKey(e.target.value)}
          placeholder="AKIAIOSFODNN7EXAMPLE"
          className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 font-mono text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none" />
      </div>
      <div>
        <label className="mb-1.5 block text-xs font-medium text-zinc-300">
          Secret Key <span className="text-red-400">*</span>
        </label>
        <input type="password" required={!s3Config?.configured} value={s3SecretKey}
          onChange={(e) => setS3SecretKey(e.target.value)}
          placeholder={s3Config?.configured ? "••••••••  (leave blank to keep)" : "wJalrXUtnFEMI/K7MDENG..."}
          className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 font-mono text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none" />
      </div>
      <div className="sm:col-span-2">
        <label className="mb-1.5 block text-xs font-medium text-zinc-300">Path Prefix</label>
        <input type="text" value={s3Prefix} onChange={(e) => setS3Prefix(e.target.value)}
          placeholder="infrakt/backups/"
          className="w-full rounded-lg border border-zinc-600 bg-zinc-700 px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-500 focus:border-orange-500 focus:ring-1 focus:ring-orange-500 focus-visible:outline-none" />
        <p className="mt-1 text-xs text-zinc-500">Optional path prefix for backup files in the bucket.</p>
      </div>
    </div>
    <div className="mt-5 flex items-center gap-3">
      <button type="submit" disabled={saveS3.isPending}
        className="flex items-center gap-2 rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-orange-500 disabled:opacity-50">
        {saveS3.isPending && <Loader2 size={14} className="animate-spin" />}
        Save
      </button>
      {s3Config?.configured && (
        <button type="button"
          onClick={async () => {
            try {
              await deleteS3.mutateAsync();
              toast.success("S3 configuration removed");
              setS3Endpoint(""); setS3Bucket(""); setS3Region("");
              setS3AccessKey(""); setS3SecretKey(""); setS3Prefix("");
            } catch (err) {
              toast.error(err instanceof Error ? err.message : "Failed to remove S3 config");
            }
          }}
          className="flex items-center gap-2 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm font-medium text-red-400 transition-colors hover:bg-red-500/20">
          <Trash2 size={14} /> Remove
        </button>
      )}
    </div>
  </form>
</section>
```

**Step 2: Run type check**

Run: `cd frontend && npm run type-check`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/pages/Settings.tsx
git commit -m "feat: add S3 Backup Storage settings section to frontend"
```

---

### Task 9: Frontend — S3 Badge in Backup List

**Files:**
- Modify: `frontend/src/pages/DatabaseDetail.tsx` (add cloud badge to backup table)

**Step 1: Add location badge to backup rows**

In `DatabaseDetail.tsx`, in the backup table `<tbody>`, add a location indicator to each row. After the filename `<td>`, add:

```tsx
<td className="px-4 py-3 text-xs">
  {backup.location === "s3" && (
    <span className="inline-flex items-center gap-1 rounded-md bg-sky-500/10 px-2 py-0.5 text-xs text-sky-300 ring-1 ring-sky-500/30">
      <Cloud size={10} /> S3
    </span>
  )}
  {backup.location === "both" && (
    <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/10 px-2 py-0.5 text-xs text-emerald-300 ring-1 ring-emerald-500/30">
      <Cloud size={10} /> S3 + Local
    </span>
  )}
  {(!backup.location || backup.location === "local") && (
    <span className="text-zinc-500">Local</span>
  )}
</td>
```

Add `"Location"` to the table header array (between "Size" and "Date"):

```tsx
{["Filename", "Size", "Location", "Date", "Actions"].map((h) => (
```

Import `Cloud` from lucide-react at the top.

**Step 2: Run type check**

Run: `cd frontend && npm run type-check`
Expected: PASS

**Step 3: Commit**

```bash
git add frontend/src/pages/DatabaseDetail.tsx
git commit -m "feat: show S3/local location badge in backup table"
```

---

### Task 10: E2E Tests — S3 Settings

**Files:**
- Modify: `frontend/e2e/fixtures.ts` (add S3 mock routes)
- Create: `frontend/e2e/s3-settings.spec.ts`

**Step 1: Add S3 mock routes to fixtures**

In `frontend/e2e/fixtures.ts`, inside `mockApi()`, add before the catchall:

```typescript
// S3 settings
await page.route("**/api/settings/s3", (route) => {
  if (route.request().method() === "GET") {
    return route.fulfill({ json: { configured: false } });
  }
  if (route.request().method() === "PUT") {
    return route.fulfill({ json: { message: "S3 configuration saved" } });
  }
  if (route.request().method() === "DELETE") {
    return route.fulfill({ json: { message: "S3 configuration removed" } });
  }
  return route.continue();
});
```

**Step 2: Write E2E tests**

Create `frontend/e2e/s3-settings.spec.ts`:

```typescript
import { test, expect } from "@playwright/test";
import { login, mockApi } from "./fixtures";

test.describe("Settings — S3 Backup Storage", () => {
  test.beforeEach(async ({ page }) => {
    await mockApi(page);
    await login(page);
    await page.goto("/settings");
  });

  test("displays S3 Backup Storage section heading", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "S3 Backup Storage" }),
    ).toBeVisible();
  });

  test("shows endpoint URL input", async ({ page }) => {
    await expect(page.getByPlaceholder("https://s3.amazonaws.com")).toBeVisible();
  });

  test("shows bucket input", async ({ page }) => {
    await expect(page.getByPlaceholder("my-backups")).toBeVisible();
  });

  test("shows access key input", async ({ page }) => {
    await expect(page.getByPlaceholder("AKIAIOSFODNN7EXAMPLE")).toBeVisible();
  });

  test("Save button is visible", async ({ page }) => {
    await expect(
      page.getByRole("button", { name: "Save" }).last(),
    ).toBeVisible();
  });

  test("saving config shows success toast", async ({ page }) => {
    await page.getByPlaceholder("https://s3.amazonaws.com").fill("https://s3.amazonaws.com");
    await page.getByPlaceholder("my-backups").fill("test-bucket");
    await page.getByPlaceholder("us-east-1").fill("us-east-1");
    await page.getByPlaceholder("AKIAIOSFODNN7EXAMPLE").fill("AKID123");
    // Secret key field — use the specific placeholder
    const secretInput = page.locator('input[type="password"]').last();
    await secretInput.fill("SECRET123");
    await page.getByRole("button", { name: "Save" }).last().click();
    await expect(page.getByText(/S3 configuration saved/)).toBeVisible();
  });

  test("shows Connected badge when configured", async ({ page }) => {
    // Override the mock to return configured
    await page.route("**/api/settings/s3", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({
          json: {
            configured: true,
            endpoint_url: "https://s3.amazonaws.com",
            bucket: "my-backups",
            region: "us-east-1",
            access_key: "AKID",
            prefix: "",
          },
        });
      }
      return route.continue();
    });
    await page.goto("/settings");
    await expect(page.getByText("Connected")).toBeVisible();
  });

  test("Remove button visible when configured", async ({ page }) => {
    await page.route("**/api/settings/s3", (route) => {
      if (route.request().method() === "GET") {
        return route.fulfill({
          json: {
            configured: true,
            endpoint_url: "https://s3.amazonaws.com",
            bucket: "b",
            region: "r",
            access_key: "k",
            prefix: "",
          },
        });
      }
      if (route.request().method() === "DELETE") {
        return route.fulfill({ json: { message: "S3 configuration removed" } });
      }
      return route.continue();
    });
    await page.goto("/settings");
    await expect(page.getByRole("button", { name: "Remove" })).toBeVisible();
  });
});
```

**Step 3: Run E2E tests**

Run: `cd frontend && npx playwright test e2e/s3-settings.spec.ts --reporter=list`
Expected: PASS

**Step 4: Commit**

```bash
git add frontend/e2e/fixtures.ts frontend/e2e/s3-settings.spec.ts
git commit -m "test: add E2E tests for S3 backup storage settings"
```

---

### Task 11: Run Full Test Suite

**Step 1: Run backend tests**

Run: `python3 -m pytest tests/unit/ -v`
Expected: All PASS

**Step 2: Run frontend type check**

Run: `cd frontend && npm run type-check`
Expected: PASS

**Step 3: Run lint**

Run: `ruff check . && ruff format --check .`
Expected: PASS (fix any issues)

**Step 4: Run E2E tests**

Run: `cd frontend && npx playwright test --reporter=list`
Expected: All PASS

**Step 5: Final commit if any fixes needed**

```bash
git add -A
git commit -m "fix: address lint/type issues from S3 backup storage implementation"
```
