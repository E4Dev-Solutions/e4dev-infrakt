import os
import stat

from cryptography.fernet import Fernet

import cli.core.config as config


def get_or_create_key() -> bytes:
    """Read or generate the master encryption key."""
    config.ensure_config_dir()
    key_path = config.MASTER_KEY_PATH
    if key_path.exists():
        return key_path.read_bytes().strip()
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    os.chmod(key_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    return key


def _fernet() -> Fernet:
    return Fernet(get_or_create_key())


def encrypt(value: str) -> str:
    """Encrypt a plaintext string, return base64 token."""
    return _fernet().encrypt(value.encode()).decode()


def decrypt(token: str) -> str:
    """Decrypt a base64 token back to plaintext."""
    return _fernet().decrypt(token.encode()).decode()


def encrypt_env_dict(env: dict[str, str]) -> dict[str, str]:
    """Encrypt all values in a dict."""
    f = _fernet()
    return {k: f.encrypt(v.encode()).decode() for k, v in env.items()}


def decrypt_env_dict(env: dict[str, str]) -> dict[str, str]:
    """Decrypt all values in a dict."""
    f = _fernet()
    return {k: f.decrypt(v.encode()).decode() for k, v in env.items()}


def env_content_for_app(app_id: int) -> str:
    """Load encrypted env vars for an app and return as plaintext .env content."""
    import json

    import cli.core.config as _config

    env_file = _config.ENVS_DIR / f"{app_id}.json"
    if not env_file.exists():
        return ""
    data: dict[str, str] = json.loads(env_file.read_text())
    lines = [f"{k}={decrypt(v)}" for k, v in sorted(data.items())]
    return "\n".join(lines) + "\n" if lines else ""
