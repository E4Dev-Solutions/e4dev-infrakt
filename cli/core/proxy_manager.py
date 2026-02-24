"""Caddy reverse proxy configuration manager."""

from __future__ import annotations

import re

from cli.core.exceptions import InfraktError
from cli.core.ssh import SSHClient

CADDYFILE_PATH = "/opt/infrakt/caddy/Caddyfile"
CADDYFILE_HEADER = "# Managed by infrakt — do not edit manually\n"

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


def _build_caddyfile(entries: list[tuple[str, int]]) -> str:
    """Build a complete Caddyfile from a list of (domain, port) tuples."""
    lines = [CADDYFILE_HEADER]
    for domain, port in sorted(entries):
        lines.extend([
            f"{domain} {{",
            f"    reverse_proxy localhost:{port}",
            "}",
            "",
        ])
    return "\n".join(lines)


def _parse_caddyfile(content: str) -> list[tuple[str, int]]:
    """Parse existing Caddyfile into (domain, port) tuples."""
    entries: list[tuple[str, int]] = []
    lines = content.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        # Look for "domain.com {"
        if line.endswith("{") and not line.startswith("#"):
            domain = line.rstrip(" {").strip()
            # Look for reverse_proxy in the block
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("}"):
                inner = lines[i].strip()
                if inner.startswith("reverse_proxy"):
                    parts = inner.split()
                    if len(parts) >= 2:
                        target = parts[1]
                        # Extract port from "localhost:PORT"
                        if ":" in target:
                            port_str = target.split(":")[-1]
                            try:
                                entries.append((domain, int(port_str)))
                            except ValueError:
                                pass
                i += 1
        i += 1
    return entries


def add_domain(ssh: SSHClient, domain: str, port: int) -> None:
    """Add a reverse proxy entry for a domain pointing to a local port."""
    _validate_domain(domain)
    _validate_port(port)
    content = ssh.read_remote_file(CADDYFILE_PATH)
    entries = _parse_caddyfile(content)

    # Replace existing or add new
    entries = [(d, p) for d, p in entries if d != domain]
    entries.append((domain, port))

    new_content = _build_caddyfile(entries)
    ssh.upload_string(new_content, CADDYFILE_PATH)
    ssh.run_checked("systemctl reload caddy")


def remove_domain(ssh: SSHClient, domain: str) -> None:
    """Remove a reverse proxy entry for a domain."""
    content = ssh.read_remote_file(CADDYFILE_PATH)
    entries = _parse_caddyfile(content)
    entries = [(d, p) for d, p in entries if d != domain]

    new_content = _build_caddyfile(entries)
    ssh.upload_string(new_content, CADDYFILE_PATH)
    ssh.run_checked("systemctl reload caddy")


def list_domains(ssh: SSHClient) -> list[tuple[str, int]]:
    """List all configured proxy entries."""
    content = ssh.read_remote_file(CADDYFILE_PATH)
    return _parse_caddyfile(content)


def reload_proxy(ssh: SSHClient) -> None:
    """Reload Caddy configuration."""
    ssh.run_checked("systemctl reload caddy")


def get_status(ssh: SSHClient) -> str:
    """Get Caddy service status."""
    stdout, _, _ = ssh.run("systemctl status caddy --no-pager -l")
    return stdout
