"""Environment variable management API routes."""

import json
import shlex
from pathlib import Path

from fastapi import APIRouter, HTTPException

from api.schemas import EnvVarOut, EnvVarSet
from cli.core.config import ENVS_DIR, ensure_config_dir
from cli.core.crypto import decrypt, encrypt
from cli.core.database import get_session, init_db
from cli.core.deployer import _validate_name
from cli.core.ssh import SSHClient
from cli.models.app import App

router = APIRouter(prefix="/apps/{app_name}/env", tags=["env"])


def _get_app_id(app_name: str) -> int:
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == app_name).first()
        if not app_obj:
            raise HTTPException(404, f"App '{app_name}' not found")
        return app_obj.id


def _env_file(app_id: int) -> Path:
    ensure_config_dir()
    return Path(ENVS_DIR) / f"{app_id}.json"


def _load_env(app_id: int) -> dict[str, str]:
    path = _env_file(app_id)
    if not path.exists():
        return {}
    content = json.loads(path.read_text())
    if isinstance(content, dict):
        return content
    return {}


def _save_env(app_id: int, data: dict[str, str]) -> None:
    _env_file(app_id).write_text(json.dumps(data, indent=2))


@router.get("", response_model=list[EnvVarOut])
def list_env(app_name: str, show_values: bool = False) -> list[EnvVarOut]:
    init_db()
    app_id = _get_app_id(app_name)
    data = _load_env(app_id)
    return [
        EnvVarOut(key=k, value=decrypt(v) if show_values else "••••••••")
        for k, v in sorted(data.items())
    ]


@router.post("", response_model=list[EnvVarOut])
def set_env(app_name: str, vars: list[EnvVarSet]) -> list[EnvVarOut]:
    init_db()
    app_id = _get_app_id(app_name)
    data = _load_env(app_id)
    for var in vars:
        data[var.key] = encrypt(var.value)
    _save_env(app_id, data)
    return [EnvVarOut(key=v.key, value="••••••••") for v in vars]


@router.delete("/{key}")
def delete_env(app_name: str, key: str) -> dict[str, str]:
    init_db()
    app_id = _get_app_id(app_name)
    data = _load_env(app_id)
    if key not in data:
        raise HTTPException(404, f"Variable '{key}' not set")
    del data[key]
    _save_env(app_id, data)
    return {"message": f"Deleted '{key}'"}


@router.post("/push")
def push_env(app_name: str) -> dict[str, str]:
    init_db()
    with get_session() as session:
        app_obj = session.query(App).filter(App.name == app_name).first()
        if not app_obj:
            raise HTTPException(404, f"App '{app_name}' not found")
        srv = app_obj.server
        ssh = SSHClient(host=srv.host, user=srv.user, port=srv.port, key_path=srv.ssh_key_path)
        app_id = app_obj.id

    data = _load_env(app_id)
    lines = [f"{k}={decrypt(v)}" for k, v in sorted(data.items())]
    env_content = "\n".join(lines) + "\n" if lines else ""

    try:
        _validate_name(app_name, "app name")
    except Exception:
        raise HTTPException(400, f"Invalid app name: {app_name!r}")
    app_path = f"/opt/infrakt/apps/{app_name}"
    q_path = shlex.quote(app_path)
    with ssh:
        ssh.upload_string(env_content, f"{app_path}/.env")
        ssh.run_checked(f"cd {q_path} && docker compose restart", timeout=60)

    return {"message": f"Pushed {len(data)} variable(s) and restarted"}
