"""HTTP health check for deployed apps."""

from __future__ import annotations

import shlex

from cli.core.ssh import SSHClient


def check_app_health(ssh: SSHClient, port: int, health_path: str) -> dict:
    """Curl the health check URL from the server.

    Constructs: http://127.0.0.1:{port}{health_path}

    Returns dict with keys:
    - healthy: bool
    - status_code: int | None
    - response_time_ms: float | None
    - error: str | None
    """
    url = f"http://127.0.0.1:{port}{health_path}"
    cmd = (
        f"curl -s -o /dev/null -w '%{{http_code}} %{{time_total}}' --max-time 10 {shlex.quote(url)}"
    )
    stdout, stderr, exit_code = ssh.run(cmd, timeout=15)

    if exit_code != 0:
        return {
            "healthy": False,
            "status_code": None,
            "response_time_ms": None,
            "error": stderr.strip() or f"curl exit code {exit_code}",
        }

    parts = stdout.strip().split()
    try:
        status_code = int(parts[0])
        response_time = float(parts[1]) * 1000  # seconds to ms
    except (IndexError, ValueError):
        return {
            "healthy": False,
            "status_code": None,
            "response_time_ms": None,
            "error": f"Unexpected curl output: {stdout.strip()!r}",
        }

    return {
        "healthy": 200 <= status_code < 400,
        "status_code": status_code,
        "response_time_ms": round(response_time, 1),
        "error": None,
    }
