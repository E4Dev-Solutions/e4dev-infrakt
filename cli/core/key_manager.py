"""SSH key generation, import, and management."""

import base64
import hashlib
import shlex
from pathlib import Path

import paramiko  # type: ignore[import-untyped]
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from cli.core.config import KEYS_DIR
from cli.core.exceptions import InfraktError, SSHConnectionError
from cli.core.ssh import SSHClient


def _get_key_fingerprint(key: paramiko.PKey) -> str:
    """Get SHA256 fingerprint of a public key."""
    if hasattr(key, "get_base64"):
        public_bytes = base64.b64decode(key.get_base64())
    else:
        public_bytes = key.get_name().encode() + key.get_base64().encode()
    sha256_hash = hashlib.sha256(public_bytes).digest()
    fingerprint_b64 = base64.b64encode(sha256_hash).decode().rstrip("=")
    return f"SHA256:{fingerprint_b64}"


def generate_key(name: str) -> tuple[Path, str]:
    """Generate a new Ed25519 SSH key pair.

    Args:
        name: Name for the key (used as filename)

    Returns:
        Tuple of (private_key_path, fingerprint)

    Raises:
        InfraktError: If key generation or filesystem operations fail
    """
    try:
        # Generate Ed25519 key using cryptography library
        private_key = Ed25519PrivateKey.generate()

        # Create keys directory if it doesn't exist
        KEYS_DIR.mkdir(parents=True, exist_ok=True)

        # Save private key in OpenSSH format
        private_path = KEYS_DIR / name
        private_bytes = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.OpenSSH,
            encryption_algorithm=serialization.NoEncryption(),
        )
        private_path.write_bytes(private_bytes)
        private_path.chmod(0o600)

        # Load back via paramiko to get public key string and fingerprint
        key = paramiko.Ed25519Key.from_private_key_file(str(private_path))
        fingerprint = _get_key_fingerprint(key)

        # Save public key
        public_path = KEYS_DIR / f"{name}.pub"
        public_key_str = f"{key.get_name()} {key.get_base64()}"
        public_path.write_text(public_key_str)
        public_path.chmod(0o644)

        return private_path, fingerprint
    except Exception as exc:
        raise InfraktError(f"Failed to generate SSH key '{name}': {exc}") from exc


def import_key(name: str, source_path: Path) -> tuple[Path, str]:
    """Import an existing SSH key into infrakt management.

    Reads the key, validates it, and stores it in KEYS_DIR.

    Args:
        name: Name for the key in infrakt
        source_path: Path to the existing private key file

    Returns:
        Tuple of (private_key_path, fingerprint)

    Raises:
        InfraktError: If key reading or import fails
    """
    try:
        source_path = Path(source_path).expanduser()
        if not source_path.exists():
            raise FileNotFoundError(f"Key file not found: {source_path}")

        # Read and validate the key
        key = paramiko.PKey.from_private_key_file(str(source_path))
        fingerprint = _get_key_fingerprint(key)

        # Create keys directory if it doesn't exist
        KEYS_DIR.mkdir(parents=True, exist_ok=True)

        # Copy private key to KEYS_DIR
        private_path = KEYS_DIR / name
        private_path.write_bytes(source_path.read_bytes())
        private_path.chmod(0o600)

        # Save public key
        public_path = KEYS_DIR / f"{name}.pub"
        public_key_str = f"{key.get_name()} {key.get_base64()}"
        public_path.write_text(public_key_str)
        public_path.chmod(0o644)

        return private_path, fingerprint
    except Exception as exc:
        raise InfraktError(f"Failed to import SSH key '{name}': {exc}") from exc


def get_fingerprint(key_path: Path) -> str:
    """Get SHA256 fingerprint of an SSH key file.

    Args:
        key_path: Path to the private key file

    Returns:
        Fingerprint in SHA256:base64 format

    Raises:
        InfraktError: If key reading fails
    """
    try:
        key_path = Path(key_path).expanduser()
        key = paramiko.PKey.from_private_key_file(str(key_path))
        return _get_key_fingerprint(key)
    except Exception as exc:
        raise InfraktError(f"Failed to read key fingerprint: {exc}") from exc


def get_public_key(key_path: Path) -> str:
    """Get the public key string from a private key file.

    Args:
        key_path: Path to the private key file

    Returns:
        Public key string (e.g., "ssh-ed25519 AAAAC3...")

    Raises:
        InfraktError: If key reading fails
    """
    try:
        key_path = Path(key_path).expanduser()
        key = paramiko.PKey.from_private_key_file(str(key_path))
        return f"{key.get_name()} {key.get_base64()}"
    except Exception as exc:
        raise InfraktError(f"Failed to read public key: {exc}") from exc


def deploy_key_to_server(ssh: SSHClient, public_key: str) -> None:
    """Deploy a public key to a server's ~/.ssh/authorized_keys.

    Appends the public key to the authorized_keys file, ensuring no duplicates.

    Args:
        ssh: SSHClient instance connected to the server
        public_key: Public key string to deploy

    Raises:
        SSHConnectionError: If SSH operations fail
    """
    try:
        # Ensure .ssh directory exists
        ssh.run_checked("mkdir -p ~/.ssh")

        # Check if key already exists
        try:
            existing = ssh.run_checked("cat ~/.ssh/authorized_keys 2>/dev/null || true")
        except SSHConnectionError:
            existing = ""

        if public_key in existing:
            return  # Already deployed

        # Append the key
        quoted_key = shlex.quote(public_key)
        ssh.run_checked(f"echo {quoted_key} >> ~/.ssh/authorized_keys")

        # Fix permissions
        ssh.run_checked("chmod 600 ~/.ssh/authorized_keys")
    except Exception as exc:
        raise SSHConnectionError(f"Failed to deploy key to server: {exc}") from exc


def remove_key_files(name: str) -> None:
    """Delete SSH key files from KEYS_DIR.

    Args:
        name: Name of the key to remove

    Raises:
        InfraktError: If deletion fails
    """
    try:
        private_path = KEYS_DIR / name
        public_path = KEYS_DIR / f"{name}.pub"

        if private_path.exists():
            private_path.unlink()
        if public_path.exists():
            public_path.unlink()
    except Exception as exc:
        raise InfraktError(f"Failed to remove key files for '{name}': {exc}") from exc
