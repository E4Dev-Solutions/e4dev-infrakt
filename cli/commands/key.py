"""Manage SSH keys."""

from pathlib import Path

import click

from cli.core.console import error, info, print_table, status_spinner, success
from cli.core.database import get_session, init_db
from cli.core.exceptions import ServerNotFoundError
from cli.core.key_manager import (
    deploy_key_to_server,
    generate_key,
    get_public_key,
    import_key,
    remove_key_files,
)
from cli.core.ssh import SSHClient
from cli.models.server import Server
from cli.models.ssh_key import SSHKey


@click.group()
def key() -> None:
    """Manage SSH keys."""


@key.command()
@click.argument("name")
def generate(name: str) -> None:
    """Generate a new Ed25519 SSH key pair."""
    init_db()

    with get_session() as session:
        existing = session.query(SSHKey).filter(SSHKey.name == name).first()
        if existing:
            error(f"SSH key '{name}' already exists")
            raise SystemExit(1)

    with status_spinner(f"Generating Ed25519 key '{name}'"):
        private_path, fingerprint = generate_key(name)
        public_key = get_public_key(private_path)

    with get_session() as session:
        ssh_key = SSHKey(
            name=name,
            fingerprint=fingerprint,
            key_type="ed25519",
            public_key=public_key,
            key_path=str(private_path),
        )
        session.add(ssh_key)

    success(f"Generated SSH key '{name}'")
    info(f"Private key: {private_path}")
    info(f"Fingerprint: {fingerprint}")


@key.command("list")
def list_keys() -> None:
    """List managed SSH keys."""
    init_db()

    with get_session() as session:
        keys = session.query(SSHKey).order_by(SSHKey.created_at).all()
        if not keys:
            info("No SSH keys managed.")
            return

        rows = [
            (
                k.name,
                k.key_type,
                k.fingerprint,
                k.created_at.strftime("%Y-%m-%d %H:%M:%S") if k.created_at else "—",
            )
            for k in keys
        ]

    print_table("SSH Keys", ["Name", "Type", "Fingerprint", "Created"], rows)


@key.command()
@click.argument("name")
@click.argument("path", type=click.Path(exists=True))
def add(name: str, path: str) -> None:
    """Import an existing SSH key into infrakt management."""
    init_db()

    with get_session() as session:
        existing = session.query(SSHKey).filter(SSHKey.name == name).first()
        if existing:
            error(f"SSH key '{name}' already exists")
            raise SystemExit(1)

    with status_spinner(f"Importing SSH key '{name}'"):
        private_path, fingerprint = import_key(name, Path(path))
        public_key = get_public_key(private_path)

    with get_session() as session:
        ssh_key = SSHKey(
            name=name,
            fingerprint=fingerprint,
            key_type="unknown",
            public_key=public_key,
            key_path=str(private_path),
        )
        session.add(ssh_key)

    success(f"Imported SSH key '{name}'")
    info(f"Private key: {private_path}")
    info(f"Fingerprint: {fingerprint}")


@key.command()
@click.argument("name")
@click.option("--force", is_flag=True, help="Skip confirmation prompt")
def remove(name: str, force: bool) -> None:
    """Remove a managed SSH key."""
    init_db()

    with get_session() as session:
        ssh_key = session.query(SSHKey).filter(SSHKey.name == name).first()
        if not ssh_key:
            error(f"SSH key '{name}' not found")
            raise SystemExit(1)

        if not force:
            confirm = click.confirm(
                f"Remove SSH key '{name}'?",
                default=False,
            )
            if not confirm:
                info("Cancelled")
                return

        session.delete(ssh_key)

    remove_key_files(name)
    success(f"Removed SSH key '{name}'")


@key.command()
@click.argument("key_name")
@click.option("--server", required=True, help="Target server name")
def deploy(key_name: str, server: str) -> None:
    """Deploy a public key to a server's authorized_keys."""
    init_db()

    # Look up the SSH key
    with get_session() as session:
        ssh_key = session.query(SSHKey).filter(SSHKey.name == key_name).first()
        if not ssh_key:
            error(f"SSH key '{key_name}' not found")
            raise SystemExit(1)
        public_key = ssh_key.public_key

    # Look up the server
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == server).first()
        if not srv:
            raise ServerNotFoundError(f"Server '{server}' not found")
        # Detach from session
        session.expunge(srv)

    # Deploy the key
    with status_spinner(f"Deploying key '{key_name}' to {server}"):
        client = SSHClient.from_server(srv)
        try:
            deploy_key_to_server(client, public_key)
        finally:
            client.close()

    success(f"Deployed key '{key_name}' to server '{server}'")
