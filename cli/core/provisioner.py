"""Server provisioning — installs Docker, Traefik, UFW, fail2ban."""

from __future__ import annotations

from collections.abc import Callable

import yaml

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
        "mkdir -p /opt/infrakt/apps /opt/infrakt/traefik/conf.d "
        "/opt/infrakt/traefik/letsencrypt /opt/infrakt/backups",
    ),
    (
        "Installing awscli",
        "pip3 install -q awscli 2>/dev/null || apt-get install -y -qq awscli 2>/dev/null || true",
    ),
    (
        "Creating Docker network",
        "docker network create infrakt 2>/dev/null || true",
    ),
]


WIPE_STEPS = [
    # ── k3s / Rancher ────────────────────────────────────────────────────
    (
        "Uninstalling k3s (if present)",
        "if [ -x /usr/local/bin/k3s-killall.sh ]; then /usr/local/bin/k3s-killall.sh; fi && "
        "if [ -x /usr/local/bin/k3s-uninstall.sh ]; then /usr/local/bin/k3s-uninstall.sh; fi && "
        "if [ -x /usr/local/bin/k3s-agent-uninstall.sh ]; then "
        "/usr/local/bin/k3s-agent-uninstall.sh; fi || true",
    ),
    (
        "Removing Rancher (if present)",
        "docker rm -f $(docker ps -a --filter name=rancher -q) 2>/dev/null || true && "
        "rm -rf /var/lib/rancher /etc/rancher 2>/dev/null || true",
    ),
    # ── Snap packages ────────────────────────────────────────────────────
    (
        "Removing snap packages (if present)",
        "if command -v snap &>/dev/null; then "
        "snap list 2>/dev/null | awk 'NR>1{print $1}' | "
        "while read pkg; do snap remove --purge \"$pkg\" 2>/dev/null || true; done; "
        "systemctl stop snapd 2>/dev/null || true; "
        "apt-get purge -y -qq snapd 2>/dev/null || true; "
        "rm -rf /snap /var/snap /var/lib/snapd ~/snap 2>/dev/null || true; "
        "fi || true",
    ),
    # ── Docker ───────────────────────────────────────────────────────────
    (
        "Stopping all Docker containers",
        "docker stop $(docker ps -aq) 2>/dev/null || true",
    ),
    (
        "Removing all Docker data",
        "docker system prune -af --volumes 2>/dev/null || true",
    ),
    (
        "Uninstalling Docker (full removal)",
        "systemctl stop docker docker.socket containerd 2>/dev/null || true && "
        "apt-get purge -y -qq docker-ce docker-ce-cli containerd.io "
        "docker-buildx-plugin docker-compose-plugin docker.io 2>/dev/null || true && "
        "rm -rf /var/lib/docker /var/lib/containerd /etc/docker 2>/dev/null || true",
    ),
    # ── Common services cleanup ──────────────────────────────────────────
    (
        "Stopping and removing common services",
        "systemctl stop nginx apache2 caddy traefik haproxy 2>/dev/null || true && "
        "apt-get purge -y -qq nginx* apache2* caddy 2>/dev/null || true",
    ),
    # ── Package cleanup ──────────────────────────────────────────────────
    (
        "Cleaning up unused packages",
        "apt-get autoremove -y -qq && apt-get clean -qq",
    ),
    # ── infrakt directories ──────────────────────────────────────────────
    (
        "Deleting /opt/infrakt",
        "rm -rf /opt/infrakt",
    ),
]


def wipe_server(
    ssh: SSHClient,
    on_step: Callable[[str, int, int], None] | None = None,
) -> None:
    """Wipe all Docker data and infrakt directories from a server.

    Args:
        ssh: Connected SSHClient instance.
        on_step: Optional callback(step_name, index, total) for progress reporting.
    """
    total = len(WIPE_STEPS)
    for idx, (step_name, command) in enumerate(WIPE_STEPS):
        if on_step:
            on_step(step_name, idx, total)
        ssh.run(command, timeout=120)


def _build_traefik_static_config(acme_email: str = "") -> str:
    """Build the Traefik static configuration YAML."""
    config: dict[str, object] = {
        "api": {
            "dashboard": True,
            "insecure": True,
        },
        "entryPoints": {
            "web": {
                "address": ":80",
                "http": {
                    "redirections": {
                        "entryPoint": {
                            "to": "websecure",
                            "scheme": "https",
                            "permanent": True,
                        }
                    }
                },
            },
            "websecure": {
                "address": ":443",
            },
        },
        "certificatesResolvers": {
            "letsencrypt": {
                "acme": {
                    "email": acme_email,
                    "storage": "/letsencrypt/acme.json",
                    "httpChallenge": {
                        "entryPoint": "web",
                    },
                }
            }
        },
        "providers": {
            "file": {
                "directory": "/opt/infrakt/traefik/conf.d",
                "watch": True,
            }
        },
        "log": {
            "level": "INFO",
        },
    }
    result: str = yaml.dump(config, default_flow_style=False, sort_keys=False)
    return result


def _build_traefik_compose() -> str:
    """Build the Traefik docker-compose.yml."""
    config: dict[str, object] = {
        "services": {
            "traefik": {
                "image": "traefik:v3.2",
                "container_name": "infrakt-traefik",
                "restart": "unless-stopped",
                "ports": [
                    "80:80",
                    "443:443",
                    "127.0.0.1:8080:8080",
                ],
                "volumes": [
                    "/opt/infrakt/traefik/traefik.yml:/etc/traefik/traefik.yml:ro",
                    "/opt/infrakt/traefik/conf.d:/opt/infrakt/traefik/conf.d:ro",
                    "/opt/infrakt/traefik/letsencrypt:/letsencrypt",
                ],
                "extra_hosts": [
                    "host.docker.internal:host-gateway",
                ],
                "networks": ["infrakt"],
            }
        },
        "networks": {
            "infrakt": {
                "external": True,
            }
        },
    }
    result: str = yaml.dump(config, default_flow_style=False, sort_keys=False)
    return result


def provision_server(
    ssh: SSHClient,
    on_step: Callable[[str, int, int], None] | None = None,
    acme_email: str = "",
) -> None:
    """Run all provisioning steps on a remote server via SSH.

    Args:
        ssh: Connected SSHClient instance.
        on_step: Optional callback(step_name, index, total) for progress reporting.
        acme_email: Email for ACME (Let's Encrypt) certificate registration.
    """
    # Count total: base steps + Traefik config steps
    traefik_steps = [
        "Setting up Traefik static config",
        "Writing Traefik docker-compose.yml",
        "Initializing ACME storage",
        "Starting Traefik",
    ]
    total = len(PROVISION_STEPS) + len(traefik_steps)
    step_idx = 0

    # Run base provisioning steps
    for step_name, command in PROVISION_STEPS:
        if on_step:
            on_step(step_name, step_idx, total)
        ssh.run_checked(command, timeout=300)
        step_idx += 1

    # Write Traefik static config
    if on_step:
        on_step("Setting up Traefik static config", step_idx, total)
    traefik_yml = _build_traefik_static_config(acme_email)
    ssh.upload_string(traefik_yml, "/opt/infrakt/traefik/traefik.yml")
    step_idx += 1

    # Write Traefik docker-compose.yml
    if on_step:
        on_step("Writing Traefik docker-compose.yml", step_idx, total)
    compose_yml = _build_traefik_compose()
    ssh.upload_string(compose_yml, "/opt/infrakt/traefik/docker-compose.yml")
    step_idx += 1

    # Initialize ACME storage
    if on_step:
        on_step("Initializing ACME storage", step_idx, total)
    ssh.run_checked(
        "touch /opt/infrakt/traefik/letsencrypt/acme.json && "
        "chmod 600 /opt/infrakt/traefik/letsencrypt/acme.json"
    )
    step_idx += 1

    # Start Traefik
    if on_step:
        on_step("Starting Traefik", step_idx, total)
    ssh.run_checked(
        "cd /opt/infrakt/traefik && docker compose up -d",
        timeout=120,
    )
