"""Server provisioning — installs Docker, Caddy, UFW, fail2ban, and creates directory structure."""

from __future__ import annotations

from collections.abc import Callable

from cli.core.ssh import SSHClient

PROVISION_STEPS = [
    (
        "Updating packages",
        "apt-get update -qq && DEBIAN_FRONTEND=noninteractive apt-get upgrade -y -qq",
    ),
    (
        "Installing Docker",
        (
            "if ! command -v docker &>/dev/null; then "
            "curl -fsSL https://get.docker.com | sh; "
            "systemctl enable docker && systemctl start docker; "
            "fi"
        ),
    ),
    (
        "Installing Caddy",
        (
            "if ! command -v caddy &>/dev/null; then "
            "apt-get install -y -qq debian-keyring debian-archive-keyring "
            "apt-transport-https curl && "
            "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' "
            "| gpg --dearmor -o "
            "/usr/share/keyrings/caddy-stable-archive-keyring.gpg && "
            "curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' "
            "| tee /etc/apt/sources.list.d/caddy-stable.list && "
            "apt-get update -qq && apt-get install -y -qq caddy; "
            "fi"
        ),
    ),
    (
        "Installing fail2ban",
        "apt-get install -y -qq fail2ban && systemctl enable fail2ban && systemctl start fail2ban",
    ),
    (
        "Configuring UFW firewall",
        (
            # Allow SSH first BEFORE enabling firewall to prevent lockout
            "apt-get install -y -qq ufw && "
            "ufw allow 22/tcp && "
            "ufw allow 80/tcp && "
            "ufw allow 443/tcp && "
            "ufw default deny incoming && "
            "ufw default allow outgoing && "
            "echo 'y' | ufw enable"
        ),
    ),
    (
        "Creating infrakt directories",
        "mkdir -p /opt/infrakt/apps /opt/infrakt/caddy /opt/infrakt/backups",
    ),
    (
        "Creating Docker network",
        "docker network create infrakt 2>/dev/null || true",
    ),
    (
        "Setting up initial Caddyfile",
        (
            "if [ ! -f /opt/infrakt/caddy/Caddyfile ]; then "
            "echo '# Managed by infrakt — do not edit manually' > /opt/infrakt/caddy/Caddyfile; "
            "fi"
        ),
    ),
    (
        "Configuring Caddy to use infrakt Caddyfile",
        (
            "mkdir -p /etc/caddy && "
            "echo 'import /opt/infrakt/caddy/Caddyfile' > /etc/caddy/Caddyfile && "
            "systemctl restart caddy"
        ),
    ),
]


def provision_server(
    ssh: SSHClient,
    on_step: Callable[[str, int, int], None] | None = None,
) -> None:
    """Run all provisioning steps on a remote server via SSH.

    Args:
        ssh: Connected SSHClient instance.
        on_step: Optional callback(step_name, index, total) for progress reporting.
    """
    total = len(PROVISION_STEPS)
    for i, (step_name, command) in enumerate(PROVISION_STEPS):
        if on_step:
            on_step(step_name, i, total)
        ssh.run_checked(command, timeout=300)
