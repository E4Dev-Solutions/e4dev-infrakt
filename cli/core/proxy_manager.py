"""Traefik reverse proxy configuration manager using file provider."""

from __future__ import annotations

import re
import socket

import yaml

from cli.core.console import warning
from cli.core.exceptions import InfraktError
from cli.core.ssh import SSHClient

CONF_DIR = "/opt/infrakt/traefik/conf.d"

# Validates domain names: alphanumeric, dots, hyphens, optional wildcard prefix
_DOMAIN_RE = re.compile(
    r"^(\*\.)?[a-zA-Z0-9]([a-zA-Z0-9-]*[a-zA-Z0-9])?(\.[a-zA-Z0-9]"
    r"([a-zA-Z0-9-]*[a-zA-Z0-9])?)*$"
)


def _validate_domain(domain: str) -> None:
    if not _DOMAIN_RE.match(domain) or len(domain) > 253:
        raise InfraktError(f"Invalid domain name: {domain!r}")


def _validate_port(port: int) -> None:
    if not (1 <= port <= 65535):
        raise InfraktError(f"Invalid port: {port}. Must be 1-65535.")


def _sanitize_domain(domain: str) -> str:
    """Convert a domain to a safe filename/identifier."""
    return re.sub(r"[^a-zA-Z0-9-]", "-", domain).strip("-")


def _check_dns(domain: str) -> str | None:
    """Resolve domain and return IP, or None if unresolvable."""
    if domain.startswith("*."):
        return None
    try:
        return socket.gethostbyname(domain)
    except socket.gaierror:
        return None


def _build_domain_config(domain: str, port: int, *, app_name: str | None = None) -> str:
    """Build Traefik dynamic config YAML for a single domain."""
    sanitized = _sanitize_domain(domain)
    router_name = sanitized
    service_name = f"svc-{sanitized}"

    # Route to the app container by name on the shared infrakt network.
    # Falls back to host.docker.internal for non-app routes (e.g. manual proxy add).
    backend_host = f"infrakt-{app_name}" if app_name else "host.docker.internal"

    config: dict[str, object] = {
        "http": {
            "routers": {
                router_name: {
                    "rule": f"Host(`{domain}`)",
                    "entryPoints": ["websecure"],
                    "service": service_name,
                    "tls": {"certResolver": "letsencrypt"},
                },
                f"{router_name}-http": {
                    "rule": f"Host(`{domain}`)",
                    "entryPoints": ["web"],
                    "service": service_name,
                },
            },
            "services": {
                service_name: {
                    "loadBalancer": {
                        "servers": [{"url": f"http://{backend_host}:{port}"}],
                        "passHostHeader": True,
                    }
                }
            },
        }
    }
    result: str = yaml.dump(config, default_flow_style=False, sort_keys=False)
    return result


def _conf_path(domain: str) -> str:
    """Return the remote config file path for a domain."""
    return f"{CONF_DIR}/{_sanitize_domain(domain)}.yml"


def add_domain(ssh: SSHClient, domain: str, port: int, *, app_name: str | None = None) -> None:
    """Add a reverse proxy route for a domain pointing to a local port.

    Writes a Traefik file provider config to conf.d/. No reload needed —
    Traefik watches the directory automatically.
    """
    _validate_domain(domain)
    _validate_port(port)

    ip = _check_dns(domain)
    if ip is None:
        warning(f"DNS for '{domain}' does not resolve yet — proxy will work once DNS propagates")

    content = _build_domain_config(domain, port, app_name=app_name)
    ssh.upload_string(content, _conf_path(domain))


def remove_domain(ssh: SSHClient, domain: str) -> None:
    """Remove a reverse proxy route for a domain."""
    path = _conf_path(domain)
    ssh.run_checked(f"rm -f {path}")


def list_domains(ssh: SSHClient) -> list[tuple[str, int]]:
    """List all configured proxy entries by reading conf.d/*.yml files."""
    stdout, _, exit_code = ssh.run(f"ls {CONF_DIR}/*.yml 2>/dev/null")
    if exit_code != 0 or not stdout.strip():
        return []

    entries: list[tuple[str, int]] = []
    for filepath in stdout.strip().splitlines():
        filepath = filepath.strip()
        if not filepath:
            continue
        content = ssh.read_remote_file(filepath)
        try:
            data = yaml.safe_load(content)
            services = data.get("http", {}).get("services", {})
            for _svc_name, svc_conf in services.items():
                servers = svc_conf.get("loadBalancer", {}).get("servers", [])
                if servers:
                    url = servers[0].get("url", "")
                    # Extract port from "http://host.docker.internal:PORT"
                    if ":" in url:
                        port_str = url.rsplit(":", 1)[-1].rstrip("/")
                        port = int(port_str)
                        # Extract domain from router rule
                        routers = data.get("http", {}).get("routers", {})
                        for _r_name, r_conf in routers.items():
                            rule = r_conf.get("rule", "")
                            if rule.startswith("Host(`") and rule.endswith("`)"):
                                domain = rule[6:-2]
                                entries.append((domain, port))
                                break
                        break
        except (yaml.YAMLError, ValueError, KeyError, IndexError):
            continue
    return entries


def reload_proxy(ssh: SSHClient) -> None:
    """Nudge Traefik to reload config. Usually not needed — file provider auto-reloads."""
    ssh.run("docker kill --signal HUP infrakt-traefik 2>/dev/null || true")


def get_status(ssh: SSHClient) -> str:
    """Get Traefik container status."""
    stdout, _, exit_code = ssh.run(
        'docker inspect infrakt-traefik --format "{{.State.Status}}" 2>/dev/null'
    )
    status = stdout.strip() if exit_code == 0 else "not running"

    # Try to get overview from Traefik API
    api_out, _, api_code = ssh.run("curl -sf http://localhost:8080/api/overview 2>/dev/null")
    if api_code == 0 and api_out.strip():
        return f"Container: {status}\nAPI: {api_out.strip()}"
    return f"Container: {status}"


def validate_domain_config(ssh: SSHClient, domain: str) -> bool:
    """Check if Traefik has picked up a domain config via its API."""
    router_name = f"{_sanitize_domain(domain)}@file"
    stdout, _, exit_code = ssh.run(
        f"curl -sf http://localhost:8080/api/http/routers/{router_name} 2>/dev/null"
    )
    return exit_code == 0 and domain in stdout
