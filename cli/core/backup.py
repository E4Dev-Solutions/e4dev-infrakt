"""Database backup and restore operations via SSH."""

from __future__ import annotations

import re
import shlex
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from cli.core.exceptions import SSHConnectionError

if TYPE_CHECKING:
    from cli.core.ssh import SSHClient
    from cli.models.app import App


def _extract_db_type(app: App) -> str:
    """Extract the database type from app_type (e.g. 'db:postgres' → 'postgres')."""
    if not app.app_type.startswith("db:"):
        raise ValueError(f"App '{app.name}' is not a database (type: {app.app_type})")
    return app.app_type.split(":", 1)[1]


def _container_name(app: App) -> str:
    """Return the Docker container name for a database app."""
    # Template child DBs use "infrakt-{name}" (e.g. infrakt-n8n-db),
    # while standalone DBs use "infrakt-db-{name}" (from db-compose.yml.j2).
    if app.parent_app_id is not None:
        return f"infrakt-{app.name}"
    return f"infrakt-db-{app.name}"


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _backup_filename(
    server_name: str, db_name: str, db_type: str, backup_id: str, ts: str, ext: str
) -> str:
    """Build a backup filename: ``{server}_{db}_{type}_{id}_{ts}.{ext}``."""
    return f"{server_name}_{db_name}_{db_type}_{backup_id}_{ts}.{ext}"


def _get_container_env(ssh: SSHClient, container: str, var: str) -> str:
    """Read an environment variable from a running container."""
    q_container = shlex.quote(container)
    q_var = shlex.quote(var)
    stdout = ssh.run_checked(f"docker exec {q_container} printenv {q_var}", timeout=10)
    return stdout.strip()


def backup_database(
    ssh: SSHClient,
    db_app: App,
    server_name: str = "",
    backup_dir: str = "/opt/infrakt/backups",
) -> str:
    """Run a backup on the remote server and return the remote file path.

    Supports postgres, mysql, redis, and mongo.
    """
    db_type = _extract_db_type(db_app)
    container = _container_name(db_app)
    q_container = shlex.quote(container)
    ts = _timestamp()
    backup_id = db_app.backup_id or "unknown"
    q_backup_dir = shlex.quote(backup_dir)

    ssh.run_checked(f"mkdir -p {q_backup_dir}")

    if db_type == "postgres":
        db_user = _get_container_env(ssh, container, "POSTGRES_USER")
        db_name = _get_container_env(ssh, container, "POSTGRES_DB")
        q_user = shlex.quote(db_user)
        q_db = shlex.quote(db_name)
        filename = _backup_filename(server_name, db_app.name, db_type, backup_id, ts, "dump")
        q_file = shlex.quote(f"{backup_dir}/{filename}")
        cmd = f"docker exec {q_container} pg_dump -Fc -U {q_user} {q_db} > {q_file}"
    elif db_type == "mysql":
        password = _get_container_env(ssh, container, "MYSQL_PASSWORD")
        q_pass = shlex.quote(password)
        mysql_user = _get_container_env(ssh, container, "MYSQL_USER")
        mysql_db = _get_container_env(ssh, container, "MYSQL_DATABASE")
        q_user = shlex.quote(mysql_user)
        q_db = shlex.quote(mysql_db)
        filename = _backup_filename(server_name, db_app.name, db_type, backup_id, ts, "sql.gz")
        q_file = shlex.quote(f"{backup_dir}/{filename}")
        cmd = f"docker exec {q_container} mysqldump -u {q_user} -p{q_pass} {q_db} | gzip > {q_file}"
    elif db_type == "redis":
        filename = _backup_filename(server_name, db_app.name, db_type, backup_id, ts, "rdb")
        q_file = shlex.quote(f"{backup_dir}/{filename}")
        # Trigger a save, then copy the dump file out
        ssh.run_checked(f"docker exec {q_container} redis-cli BGSAVE", timeout=30)
        # Wait briefly for the save to complete
        ssh.run("sleep 2")
        cmd = f"docker cp {q_container}:/data/dump.rdb {q_file}"
    elif db_type == "mongo":
        password = _get_container_env(ssh, container, "MONGO_INITDB_ROOT_PASSWORD")
        q_pass = shlex.quote(password)
        mongo_user = _get_container_env(ssh, container, "MONGO_INITDB_ROOT_USERNAME")
        q_user = shlex.quote(mongo_user)
        filename = _backup_filename(server_name, db_app.name, db_type, backup_id, ts, "archive.gz")
        q_file = shlex.quote(f"{backup_dir}/{filename}")
        cmd = (
            f"docker exec {q_container} mongodump"
            f" --archive --gzip"
            f" -u {q_user} -p {q_pass}"
            f" --authenticationDatabase admin"
            f" > {q_file}"
        )
    else:
        raise ValueError(f"Unsupported database type for backup: {db_type}")

    ssh.run_checked(cmd, timeout=300)
    return f"{backup_dir}/{filename}"


def restore_database(
    ssh: SSHClient,
    db_app: App,
    remote_backup_path: str,
) -> None:
    """Restore a database from a backup file on the remote server.

    The backup file must already exist at ``remote_backup_path``.
    """
    db_type = _extract_db_type(db_app)
    container = _container_name(db_app)
    q_container = shlex.quote(container)
    q_path = shlex.quote(remote_backup_path)

    # Verify backup file exists
    _, _, rc = ssh.run(f"test -f {q_path}")
    if rc != 0:
        raise SSHConnectionError(f"Backup file not found on server: {remote_backup_path}")

    if db_type == "postgres":
        db_user = _get_container_env(ssh, container, "POSTGRES_USER")
        db_name = _get_container_env(ssh, container, "POSTGRES_DB")
        q_user = shlex.quote(db_user)
        q_db = shlex.quote(db_name)
        if remote_backup_path.endswith(".sql.gz"):
            # Legacy plain-SQL backup — fall back to gunzip | psql
            cmd = f"gunzip -c {q_path} | docker exec -i {q_container} psql -U {q_user} -d {q_db}"
        else:
            # Custom-format backup — use pg_restore with safe flags
            cmd = (
                f"cat {q_path} | docker exec -i {q_container}"
                f" pg_restore -U {q_user} -d {q_db} --clean --if-exists --no-owner"
            )
    elif db_type == "mysql":
        password = _get_container_env(ssh, container, "MYSQL_PASSWORD")
        q_pass = shlex.quote(password)
        mysql_user = _get_container_env(ssh, container, "MYSQL_USER")
        mysql_db = _get_container_env(ssh, container, "MYSQL_DATABASE")
        q_user = shlex.quote(mysql_user)
        q_db = shlex.quote(mysql_db)
        cmd = (
            f"gunzip -c {q_path} | docker exec -i {q_container} mysql -u {q_user} -p{q_pass} {q_db}"
        )
    elif db_type == "redis":
        # Stop redis, replace dump.rdb, restart
        app_path = f"/opt/infrakt/apps/{db_app.name}"
        q_app_path = shlex.quote(app_path)
        ssh.run_checked(f"docker cp {q_path} {q_container}:/data/dump.rdb", timeout=30)
        ssh.run_checked(f"cd {q_app_path} && docker compose restart", timeout=60)
        return
    elif db_type == "mongo":
        password = _get_container_env(ssh, container, "MONGO_INITDB_ROOT_PASSWORD")
        q_pass = shlex.quote(password)
        mongo_user = _get_container_env(ssh, container, "MONGO_INITDB_ROOT_USERNAME")
        q_user = shlex.quote(mongo_user)
        cmd = (
            f"cat {q_path}"
            f" | docker exec -i {q_container} mongorestore"
            f" --archive --gzip --drop"
            f" -u {q_user} -p {q_pass}"
            f" --authenticationDatabase admin"
        )
    else:
        raise ValueError(f"Unsupported database type for restore: {db_type}")

    ssh.run_checked(cmd, timeout=300)


# ---------------------------------------------------------------------------
# Scheduled backups via cron
# ---------------------------------------------------------------------------


def _cron_marker(app: App) -> str:
    """Return the unique marker used to identify this app's backup cron entry."""
    return f"infrakt-backup:{app.name}"


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
    server_name: str = "",
) -> str:
    """Generate a shell script that performs a backup and cleans old files."""
    db_type = _extract_db_type(db_app)
    container = _container_name(db_app)
    name = db_app.name
    backup_id = db_app.backup_id or "unknown"
    ts_var = "$(date +%Y%m%d_%H%M%S)"
    base = f"{name}_{db_type}_{backup_id}"
    fname_prefix = f"{server_name}_{base}" if server_name else base

    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"BACKUP_DIR={shlex.quote(backup_dir)}",
        'mkdir -p "$BACKUP_DIR"',
        "",
    ]

    if db_type == "postgres":
        filename = f"{fname_prefix}_{ts_var}.dump"
        q_c = shlex.quote(container)
        q_n = shlex.quote(name)
        lines.append(f'docker exec {q_c} pg_dump -Fc -U {q_n} {q_n} > "$BACKUP_DIR/{filename}"')
    elif db_type == "mysql":
        lines.append(f"MYSQL_PASS=$(docker exec {shlex.quote(container)} printenv MYSQL_PASSWORD)")
        filename = f"{fname_prefix}_{ts_var}.sql.gz"
        lines.append(
            f"docker exec {shlex.quote(container)} mysqldump -u {shlex.quote(name)}"
            f' -p"$MYSQL_PASS" {shlex.quote(name)}'
            f' | gzip > "$BACKUP_DIR/{filename}"'
        )
    elif db_type == "redis":
        filename = f"{fname_prefix}_{ts_var}.rdb"
        lines.extend(
            [
                f"docker exec {shlex.quote(container)} redis-cli BGSAVE",
                "sleep 2",
                f'docker cp {shlex.quote(container)}:/data/dump.rdb "$BACKUP_DIR/{filename}"',
            ]
        )
    elif db_type == "mongo":
        q_c = shlex.quote(container)
        lines.append(f"MONGO_PASS=$(docker exec {q_c} printenv MONGO_INITDB_ROOT_PASSWORD)")
        filename = f"{fname_prefix}_{ts_var}.archive.gz"
        lines.append(
            f"docker exec {shlex.quote(container)} mongodump"
            f" --archive --gzip"
            f' -u {shlex.quote(name)} -p "$MONGO_PASS"'
            f" --authenticationDatabase admin"
            f' > "$BACKUP_DIR/{filename}"'
        )
    else:
        raise ValueError(f"Unsupported database type for scheduled backup: {db_type}")

    # Retention: delete files older than N days matching this app's pattern
    lines.extend(
        [
            "",
            "# Clean up old backups",
            f'find "$BACKUP_DIR" -name {shlex.quote(f"*_{backup_id}_*")}'
            f" -mtime +{retention_days} -delete",
        ]
    )

    # S3 upload (optional)
    if s3_endpoint and s3_bucket and s3_access_key and s3_secret_key:
        s3_dir = f"{s3_prefix}{db_type}/" if s3_prefix else f"{db_type}/"
        s3_key = f"{s3_dir}{filename}"
        lines.extend(
            [
                "",
                "# Upload to S3",
                f"export AWS_ACCESS_KEY_ID={shlex.quote(s3_access_key)}",
                f"export AWS_SECRET_ACCESS_KEY={shlex.quote(s3_secret_key)}",
                f"export AWS_DEFAULT_REGION={shlex.quote(s3_region or '')}",
                f'aws s3 cp "$BACKUP_DIR/{filename}" {shlex.quote(f"s3://{s3_bucket}/{s3_key}")} '
                f"--endpoint-url {shlex.quote(s3_endpoint)} || true",
                "unset AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_DEFAULT_REGION",
            ]
        )

    return "\n".join(lines) + "\n"


def install_backup_cron(
    ssh: SSHClient,
    db_app: App,
    cron_expr: str,
    retention_days: int = 7,
    backup_dir: str = "/opt/infrakt/backups",
    s3_endpoint: str | None = None,
    s3_bucket: str | None = None,
    s3_region: str | None = None,
    s3_access_key: str | None = None,
    s3_secret_key: str | None = None,
    s3_prefix: str = "",
    server_name: str = "",
) -> None:
    """Upload a backup script and install a cron entry on the remote server."""
    script = generate_backup_script(
        db_app,
        backup_dir,
        retention_days,
        s3_endpoint=s3_endpoint,
        s3_bucket=s3_bucket,
        s3_region=s3_region,
        s3_access_key=s3_access_key,
        s3_secret_key=s3_secret_key,
        s3_prefix=s3_prefix,
        server_name=server_name,
    )
    script_path = f"{backup_dir}/backup-{db_app.name}.sh"
    q_script = shlex.quote(script_path)
    marker = _cron_marker(db_app)
    q_marker = shlex.quote(marker)

    ssh.run_checked(f"mkdir -p {shlex.quote(backup_dir)}")
    ssh.upload_string(script, script_path)
    ssh.run_checked(f"chmod +x {q_script}")

    # Install cron idempotently: remove old entry, add new one
    cron_line = f"{cron_expr} {script_path} # {marker}"
    ssh.run_checked(
        f"(crontab -l 2>/dev/null | grep -v {q_marker}; echo {shlex.quote(cron_line)}) | crontab -"
    )


def remove_backup_cron(
    ssh: SSHClient,
    db_app: App,
    backup_dir: str = "/opt/infrakt/backups",
) -> None:
    """Remove the cron entry and backup script from the remote server."""
    marker = _cron_marker(db_app)
    q_marker = shlex.quote(marker)
    script_path = f"{backup_dir}/backup-{db_app.name}.sh"
    q_script = shlex.quote(script_path)

    # Remove cron entry
    ssh.run(f"crontab -l 2>/dev/null | grep -v {q_marker} | crontab -")
    # Remove script file
    ssh.run(f"rm -f {q_script}")


# ---------------------------------------------------------------------------
# List backups
# ---------------------------------------------------------------------------


def _human_size(size_bytes: int) -> str:
    """Convert bytes to a human-readable size string."""
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.1f} GB"
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


def list_backups(
    ssh: SSHClient,
    db_app: App,
    backup_dir: str = "/opt/infrakt/backups",
) -> list[dict[str, str | int]]:
    """List backup files for a database on the remote server.

    Returns a list of dicts with keys: filename, size, size_bytes, modified.
    Results are sorted newest-first. Returns an empty list if no backups exist
    or the directory is missing.
    """
    q_dir = shlex.quote(backup_dir)
    # Match both old-style ({db}_*) and new-style (*__{db}_*) filenames
    q_pattern = shlex.quote(f"*{db_app.name}_*")

    # GNU find -printf: filename\tsize_bytes\tmtime_epoch
    stdout, _, rc = ssh.run(
        f"find {q_dir} -maxdepth 1 -name {q_pattern} -type f"
        f" -printf '%f\\t%s\\t%T@\\n' 2>/dev/null"
        f" | sort -t$'\\t' -k3 -rn"
    )
    if rc != 0 or not stdout.strip():
        return []

    results: list[dict[str, str | int]] = []
    for line in stdout.strip().splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        fname, size_str, mtime_str = parts
        try:
            size_bytes = int(size_str)
            epoch = float(mtime_str.split(".")[0])
        except (ValueError, IndexError):
            continue
        dt = datetime.fromtimestamp(epoch, tz=UTC)
        results.append(
            {
                "filename": fname,
                "size": _human_size(size_bytes),
                "size_bytes": size_bytes,
                "modified": dt.isoformat(),
            }
        )
    return results


# ---------------------------------------------------------------------------
# S3 backup operations
# ---------------------------------------------------------------------------


def _write_aws_credentials(
    ssh: SSHClient,
    access_key: str,
    secret_key: str,
    region: str,
) -> None:
    """Write temporary AWS credentials/config files on the remote server."""
    creds_content = (
        f"[default]\naws_access_key_id = {access_key}\naws_secret_access_key = {secret_key}\n"
    )
    config_content = f"[default]\nregion = {region}\n"
    ssh.upload_string(creds_content, "/tmp/.infrakt-aws-credentials")
    ssh.upload_string(config_content, "/tmp/.infrakt-aws-config")
    ssh.run("chmod 600 /tmp/.infrakt-aws-credentials /tmp/.infrakt-aws-config")


def _cleanup_aws_credentials(ssh: SSHClient) -> None:
    """Remove temporary AWS credential files."""
    ssh.run("rm -f /tmp/.infrakt-aws-credentials /tmp/.infrakt-aws-config")


def _aws_env_prefix() -> str:
    """Return environment variable prefix for aws CLI with temp credentials."""
    return (
        "AWS_SHARED_CREDENTIALS_FILE=/tmp/.infrakt-aws-credentials "
        "AWS_CONFIG_FILE=/tmp/.infrakt-aws-config "
    )


def _s3_db_dir(prefix: str, db_type: str) -> str:
    """Build the S3 key directory for a database type's backups.

    Result: ``{prefix}{db_type}/`` (or ``{db_type}/`` when *prefix* is empty).
    All backups for a given type (e.g. postgres) go in one folder; the server
    and database names are encoded in each filename.
    """
    return f"{prefix}{db_type}/" if prefix else f"{db_type}/"


def upload_backup_to_s3(
    ssh: SSHClient,
    local_path: str,
    s3_endpoint: str,
    bucket: str,
    region: str,
    access_key: str,
    secret_key: str,
    prefix: str,
    db_type: str,
) -> None:
    """Upload a backup file from the remote server to S3."""
    _write_aws_credentials(ssh, access_key, secret_key, region)
    try:
        filename = local_path.rsplit("/", 1)[-1]
        s3_dir = _s3_db_dir(prefix, db_type)
        s3_key = f"{s3_dir}{filename}"
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
    db_type: str,
    backup_dir: str = "/opt/infrakt/backups",
) -> str:
    """Download a backup file from S3 to the remote server. Returns the local path."""
    _write_aws_credentials(ssh, access_key, secret_key, region)
    try:
        s3_dir = _s3_db_dir(prefix, db_type)
        s3_key = f"{s3_dir}{filename}"
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
    db_type: str,
) -> list[dict[str, str | int]]:
    """List all backup files in S3 for a given database type."""
    _write_aws_credentials(ssh, access_key, secret_key, region)
    try:
        s3_prefix = _s3_db_dir(prefix, db_type)
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
        results.append(
            {
                "filename": fname,
                "size": _human_size(size_bytes),
                "size_bytes": size_bytes,
                "modified": date_str,
            }
        )
    return results


def _is_app_backup(filename: str, backup_id: str) -> bool:
    """Check if a filename belongs to a specific app by its backup ID.

    Matches: ``{server}_{db}_{type}_{id}_{YYYYMMDD}_{HHMMSS}.{ext}``
    """
    pattern = rf"_{re.escape(backup_id)}_\d{{8}}_\d{{6}}\."
    return bool(re.search(pattern, filename))


def cleanup_old_s3_backups(
    ssh: SSHClient,
    s3_endpoint: str,
    bucket: str,
    region: str,
    access_key: str,
    secret_key: str,
    prefix: str,
    db_type: str,
    backup_id: str = "",
    keep: int = 10,
    max_age_days: int = 0,
) -> int:
    """Delete old S3 backups, keeping the most recent ``keep``.

    The **latest** backup is always preserved regardless of count or age
    limits.  Only files matching this app's ``backup_id`` are considered.

    When *max_age_days* > 0, candidates older than the cutoff are also
    marked for deletion (but the latest is still kept).

    Returns the number of files deleted.
    """
    from datetime import timedelta

    backups = list_s3_backups(
        ssh, s3_endpoint, bucket, region, access_key, secret_key, prefix, db_type
    )
    backups = [b for b in backups if _is_app_backup(str(b["filename"]), backup_id)]
    # Sort newest-first
    backups.sort(key=lambda b: str(b.get("modified", "")), reverse=True)

    # Always keep at least the latest backup
    if len(backups) <= 1:
        return 0

    candidates = backups[1:]  # everything except the latest

    # Build deletion set
    delete_filenames: set[str] = set()

    # Count-based: keep only `keep - 1` candidates (latest already kept)
    if len(candidates) > keep - 1:
        for b in candidates[keep - 1 :]:
            delete_filenames.add(str(b["filename"]))

    # Age-based: mark candidates older than cutoff
    if max_age_days > 0:
        cutoff = (datetime.now(UTC) - timedelta(days=max_age_days)).strftime("%Y-%m-%d %H:%M:%S")
        for b in candidates:
            if str(b.get("modified", "")) < cutoff:
                delete_filenames.add(str(b["filename"]))

    if not delete_filenames:
        return 0

    _write_aws_credentials(ssh, access_key, secret_key, region)
    try:
        s3_dir = _s3_db_dir(prefix, db_type)
        q_endpoint = shlex.quote(s3_endpoint)
        deleted = 0
        for fn in delete_filenames:
            s3_key = f"s3://{bucket}/{s3_dir}{fn}"
            cmd = f"{_aws_env_prefix()}aws s3 rm {shlex.quote(s3_key)} --endpoint-url {q_endpoint}"
            _, _, rc = ssh.run(cmd, timeout=30)
            if rc == 0:
                deleted += 1
    finally:
        _cleanup_aws_credentials(ssh)
    return deleted
