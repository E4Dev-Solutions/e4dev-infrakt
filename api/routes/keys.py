"""SSH key management API routes."""

from fastapi import APIRouter, HTTPException

from api.schemas import SSHKeyDeploy, SSHKeyGenerate, SSHKeyOut
from cli.core.database import get_session, init_db
from cli.core.exceptions import SSHConnectionError
from cli.core.key_manager import (
    deploy_key_to_server,
    generate_key,
    get_public_key,
    remove_key_files,
)
from cli.core.ssh import SSHClient
from cli.models.server import Server
from cli.models.ssh_key import SSHKey

router = APIRouter(prefix="/keys", tags=["keys"])


def _ssh_key_out(key: SSHKey) -> SSHKeyOut:
    """Convert SSHKey model to SSHKeyOut schema."""
    return SSHKeyOut(
        id=key.id,
        name=key.name,
        fingerprint=key.fingerprint,
        key_type=key.key_type,
        public_key=key.public_key,
        created_at=key.created_at,
    )


@router.get("", response_model=list[SSHKeyOut])
def list_keys() -> list[SSHKeyOut]:
    """List all managed SSH keys."""
    init_db()
    with get_session() as session:
        keys = session.query(SSHKey).order_by(SSHKey.created_at).all()
        return [_ssh_key_out(k) for k in keys]


@router.post("", response_model=SSHKeyOut, status_code=201)
def create_key(body: SSHKeyGenerate) -> SSHKeyOut:
    """Generate a new Ed25519 SSH key pair."""
    init_db()

    with get_session() as session:
        existing = session.query(SSHKey).filter(SSHKey.name == body.name).first()
        if existing:
            raise HTTPException(409, f"SSH key '{body.name}' already exists")

    try:
        private_path, fingerprint = generate_key(body.name)
        public_key = get_public_key(private_path)
    except Exception as exc:
        raise HTTPException(400, f"Key generation failed: {str(exc)}")

    with get_session() as session:
        ssh_key = SSHKey(
            name=body.name,
            fingerprint=fingerprint,
            key_type="ed25519",
            public_key=public_key,
            key_path=str(private_path),
        )
        session.add(ssh_key)
        session.flush()
        return _ssh_key_out(ssh_key)


@router.post("/{name}/deploy", status_code=200)
def deploy_key(name: str, body: SSHKeyDeploy) -> dict[str, str]:
    """Deploy a public key to a server's authorized_keys."""
    init_db()

    # Look up the SSH key
    with get_session() as session:
        ssh_key = session.query(SSHKey).filter(SSHKey.name == name).first()
        if not ssh_key:
            raise HTTPException(404, f"SSH key '{name}' not found")
        public_key = ssh_key.public_key

    # Look up the server
    with get_session() as session:
        srv = session.query(Server).filter(Server.name == body.server_name).first()
        if not srv:
            raise HTTPException(404, f"Server '{body.server_name}' not found")
        # Detach from session
        session.expunge(srv)

    # Deploy the key
    try:
        client = SSHClient.from_server(srv)
        try:
            deploy_key_to_server(client, public_key)
        finally:
            client.close()
    except SSHConnectionError as exc:
        raise HTTPException(500, f"Failed to deploy key: {str(exc)}")

    return {"message": f"Key '{name}' deployed to server '{body.server_name}'"}


@router.delete("/{name}", status_code=200)
def delete_key(name: str) -> dict[str, str]:
    """Remove a managed SSH key."""
    init_db()

    with get_session() as session:
        ssh_key = session.query(SSHKey).filter(SSHKey.name == name).first()
        if not ssh_key:
            raise HTTPException(404, f"SSH key '{name}' not found")
        session.delete(ssh_key)

    try:
        remove_key_files(name)
    except Exception as exc:
        raise HTTPException(500, f"Failed to remove key files: {str(exc)}")

    return {"message": f"SSH key '{name}' removed"}
