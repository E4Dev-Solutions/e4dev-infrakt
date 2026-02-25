"""Live database statistics via SSH Docker exec."""

from __future__ import annotations

import shlex

from cli.core.ssh import SSHClient


def get_database_stats(ssh: SSHClient, app_name: str, db_type: str) -> dict:
    """Query database-specific stats via Docker exec.

    Returns dict with keys: disk_size, active_connections, version, uptime.
    All values are strings or None.
    """
    container = f"infrakt-db-{app_name}"
    q_container = shlex.quote(container)

    stats: dict[str, str | int | None] = {
        "disk_size": None,
        "active_connections": None,
        "version": None,
        "uptime": None,
    }

    if db_type == "postgres":
        _postgres_stats(ssh, q_container, app_name, stats)
    elif db_type == "mysql":
        _mysql_stats(ssh, q_container, stats)
    elif db_type == "redis":
        _redis_stats(ssh, q_container, stats)
    elif db_type == "mongo":
        _mongo_stats(ssh, q_container, stats)

    return stats


def _postgres_stats(ssh: SSHClient, container: str, db_name: str, stats: dict) -> None:
    q_name = shlex.quote(db_name)

    # Database size
    stdout, _, code = ssh.run(
        f"docker exec {container} psql -U {q_name} -d {q_name} -t -c "
        f'"SELECT pg_size_pretty(pg_database_size({shlex.quote(repr(db_name))}))"',
        timeout=10,
    )
    if code == 0 and stdout.strip():
        stats["disk_size"] = stdout.strip()

    # Active connections
    stdout, _, code = ssh.run(
        f"docker exec {container} psql -U {q_name} -d {q_name} -t -c "
        f'"SELECT count(*) FROM pg_stat_activity"',
        timeout=10,
    )
    if code == 0 and stdout.strip():
        try:
            stats["active_connections"] = int(stdout.strip())
        except ValueError:
            pass

    # Version
    stdout, _, code = ssh.run(
        f'docker exec {container} psql -U {q_name} -d {q_name} -t -c "SHOW server_version"',
        timeout=10,
    )
    if code == 0 and stdout.strip():
        stats["version"] = stdout.strip()

    # Uptime
    stdout, _, code = ssh.run(
        f"docker exec {container} psql -U {q_name} -d {q_name} -t -c "
        f'"SELECT now() - pg_postmaster_start_time()"',
        timeout=10,
    )
    if code == 0 and stdout.strip():
        stats["uptime"] = stdout.strip()


def _mysql_stats(ssh: SSHClient, container: str, stats: dict) -> None:
    # Version
    stdout, _, code = ssh.run(
        f'docker exec {container} mysql -u root -e "SELECT VERSION()" -s -N',
        timeout=10,
    )
    if code == 0 and stdout.strip():
        stats["version"] = stdout.strip()

    # Active connections
    stdout, _, code = ssh.run(
        f"docker exec {container} mysql -u root -e \"SHOW STATUS LIKE 'Threads_connected'\" -s -N",
        timeout=10,
    )
    if code == 0 and stdout.strip():
        parts = stdout.strip().split()
        if len(parts) >= 2:
            try:
                stats["active_connections"] = int(parts[1])
            except ValueError:
                pass

    # Uptime
    stdout, _, code = ssh.run(
        f"docker exec {container} mysql -u root -e \"SHOW STATUS LIKE 'Uptime'\" -s -N",
        timeout=10,
    )
    if code == 0 and stdout.strip():
        parts = stdout.strip().split()
        if len(parts) >= 2:
            try:
                secs = int(parts[1])
                hours = secs // 3600
                mins = (secs % 3600) // 60
                stats["uptime"] = f"{hours}h {mins}m"
            except ValueError:
                pass


def _redis_stats(ssh: SSHClient, container: str, stats: dict) -> None:
    # Memory
    stdout, _, code = ssh.run(
        f"docker exec {container} redis-cli INFO memory",
        timeout=10,
    )
    if code == 0:
        for line in stdout.splitlines():
            if line.startswith("used_memory_human:"):
                stats["disk_size"] = line.split(":", 1)[1].strip()
                break

    # Connected clients
    stdout, _, code = ssh.run(
        f"docker exec {container} redis-cli INFO clients",
        timeout=10,
    )
    if code == 0:
        for line in stdout.splitlines():
            if line.startswith("connected_clients:"):
                try:
                    stats["active_connections"] = int(line.split(":", 1)[1].strip())
                except ValueError:
                    pass
                break

    # Version
    stdout, _, code = ssh.run(
        f"docker exec {container} redis-cli INFO server",
        timeout=10,
    )
    if code == 0:
        for line in stdout.splitlines():
            if line.startswith("redis_version:"):
                stats["version"] = line.split(":", 1)[1].strip()
                break
            if line.startswith("uptime_in_seconds:"):
                try:
                    secs = int(line.split(":", 1)[1].strip())
                    hours = secs // 3600
                    mins = (secs % 3600) // 60
                    stats["uptime"] = f"{hours}h {mins}m"
                except ValueError:
                    pass


def _mongo_stats(ssh: SSHClient, container: str, stats: dict) -> None:
    import json

    # Version
    stdout, _, code = ssh.run(
        f'docker exec {container} mongosh --quiet --eval "db.version()"',
        timeout=10,
    )
    if code == 0 and stdout.strip():
        stats["version"] = stdout.strip()

    # Stats (size + connections)
    stdout, _, code = ssh.run(
        f'docker exec {container} mongosh --quiet --eval "JSON.stringify(db.serverStatus())"',
        timeout=10,
    )
    if code == 0 and stdout.strip():
        try:
            data = json.loads(stdout.strip())
            conns = data.get("connections", {}).get("current")
            if conns is not None:
                stats["active_connections"] = conns
            uptime = data.get("uptime")
            if uptime is not None:
                hours = int(uptime) // 3600
                mins = (int(uptime) % 3600) // 60
                stats["uptime"] = f"{hours}h {mins}m"
        except (json.JSONDecodeError, ValueError):
            pass
