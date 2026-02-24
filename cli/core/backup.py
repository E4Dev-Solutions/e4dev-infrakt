"""Database backup and restore operations via SSH."""

from __future__ import annotations

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
    return f"infrakt-db-{app.name}"


def _timestamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%d_%H%M%S")


def _get_container_env(ssh: SSHClient, container: str, var: str) -> str:
    """Read an environment variable from a running container."""
    q_container = shlex.quote(container)
    q_var = shlex.quote(var)
    stdout = ssh.run_checked(f"docker exec {q_container} printenv {q_var}", timeout=10)
    return stdout.strip()


def backup_database(
    ssh: SSHClient,
    db_app: App,
    backup_dir: str = "/opt/infrakt/backups",
) -> str:
    """Run a backup on the remote server and return the remote file path.

    Supports postgres, mysql, redis, and mongo.
    """
    db_type = _extract_db_type(db_app)
    container = _container_name(db_app)
    q_container = shlex.quote(container)
    q_name = shlex.quote(db_app.name)
    ts = _timestamp()
    q_backup_dir = shlex.quote(backup_dir)

    ssh.run_checked(f"mkdir -p {q_backup_dir}")

    if db_type == "postgres":
        filename = f"{db_app.name}_{ts}.sql.gz"
        q_file = shlex.quote(f"{backup_dir}/{filename}")
        cmd = f"docker exec {q_container} pg_dump -U {q_name} {q_name} | gzip > {q_file}"
    elif db_type == "mysql":
        password = _get_container_env(ssh, container, "MYSQL_PASSWORD")
        q_pass = shlex.quote(password)
        filename = f"{db_app.name}_{ts}.sql.gz"
        q_file = shlex.quote(f"{backup_dir}/{filename}")
        cmd = (
            f"docker exec {q_container} mysqldump -u {q_name} -p{q_pass} {q_name} | gzip > {q_file}"
        )
    elif db_type == "redis":
        filename = f"{db_app.name}_{ts}.rdb"
        q_file = shlex.quote(f"{backup_dir}/{filename}")
        # Trigger a save, then copy the dump file out
        ssh.run_checked(f"docker exec {q_container} redis-cli BGSAVE", timeout=30)
        # Wait briefly for the save to complete
        ssh.run("sleep 2")
        cmd = f"docker cp {q_container}:/data/dump.rdb {q_file}"
    elif db_type == "mongo":
        password = _get_container_env(ssh, container, "MONGO_INITDB_ROOT_PASSWORD")
        q_pass = shlex.quote(password)
        filename = f"{db_app.name}_{ts}.archive.gz"
        q_file = shlex.quote(f"{backup_dir}/{filename}")
        cmd = (
            f"docker exec {q_container} mongodump"
            f" --archive --gzip"
            f" -u {q_name} -p {q_pass}"
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
    q_name = shlex.quote(db_app.name)
    q_path = shlex.quote(remote_backup_path)

    # Verify backup file exists
    _, _, rc = ssh.run(f"test -f {q_path}")
    if rc != 0:
        raise SSHConnectionError(f"Backup file not found on server: {remote_backup_path}")

    if db_type == "postgres":
        # Drop and recreate, then restore
        cmd = f"gunzip -c {q_path} | docker exec -i {q_container} psql -U {q_name} -d {q_name}"
    elif db_type == "mysql":
        password = _get_container_env(ssh, container, "MYSQL_PASSWORD")
        q_pass = shlex.quote(password)
        cmd = (
            f"gunzip -c {q_path}"
            f" | docker exec -i {q_container} mysql -u {q_name} -p{q_pass} {q_name}"
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
        cmd = (
            f"cat {q_path}"
            f" | docker exec -i {q_container} mongorestore"
            f" --archive --gzip --drop"
            f" -u {q_name} -p {q_pass}"
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
) -> str:
    """Generate a shell script that performs a backup and cleans old files."""
    db_type = _extract_db_type(db_app)
    container = _container_name(db_app)
    name = db_app.name
    ts_var = "$(date +%Y%m%d_%H%M%S)"

    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        f"BACKUP_DIR={shlex.quote(backup_dir)}",
        'mkdir -p "$BACKUP_DIR"',
        "",
    ]

    if db_type == "postgres":
        filename = f"{name}_{ts_var}.sql.gz"
        q_c = shlex.quote(container)
        q_n = shlex.quote(name)
        lines.append(f'docker exec {q_c} pg_dump -U {q_n} {q_n} | gzip > "$BACKUP_DIR/{filename}"')
    elif db_type == "mysql":
        lines.append(f"MYSQL_PASS=$(docker exec {shlex.quote(container)} printenv MYSQL_PASSWORD)")
        filename = f"{name}_{ts_var}.sql.gz"
        lines.append(
            f"docker exec {shlex.quote(container)} mysqldump -u {shlex.quote(name)}"
            f' -p"$MYSQL_PASS" {shlex.quote(name)}'
            f' | gzip > "$BACKUP_DIR/{filename}"'
        )
    elif db_type == "redis":
        filename = f"{name}_{ts_var}.rdb"
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
        filename = f"{name}_{ts_var}.archive.gz"
        lines.append(
            f"docker exec {shlex.quote(container)} mongodump"
            f" --archive --gzip"
            f' -u {shlex.quote(name)} -p "$MONGO_PASS"'
            f" --authenticationDatabase admin"
            f' > "$BACKUP_DIR/{filename}"'
        )
    else:
        raise ValueError(f"Unsupported database type for scheduled backup: {db_type}")

    # Retention: delete files older than N days matching this db's name pattern
    lines.extend(
        [
            "",
            "# Clean up old backups",
            f'find "$BACKUP_DIR" -name {shlex.quote(name + "_*")} -mtime +{retention_days} -delete',
        ]
    )

    return "\n".join(lines) + "\n"


def install_backup_cron(
    ssh: SSHClient,
    db_app: App,
    cron_expr: str,
    retention_days: int = 7,
    backup_dir: str = "/opt/infrakt/backups",
) -> None:
    """Upload a backup script and install a cron entry on the remote server."""
    script = generate_backup_script(db_app, backup_dir, retention_days)
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
