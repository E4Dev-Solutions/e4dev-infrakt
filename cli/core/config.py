from pathlib import Path

INFRAKT_HOME = Path.home() / ".infrakt"
DB_PATH = INFRAKT_HOME / "infrakt.db"
KEYS_DIR = INFRAKT_HOME / "keys"
ENVS_DIR = INFRAKT_HOME / "envs"
MASTER_KEY_PATH = INFRAKT_HOME / "master.key"


def ensure_config_dir() -> Path:
    """Create all infrakt config directories if they don't exist."""
    for d in (INFRAKT_HOME, KEYS_DIR, ENVS_DIR):
        d.mkdir(parents=True, exist_ok=True)
    return INFRAKT_HOME


def get_db_url() -> str:
    """Return the SQLite connection URL."""
    return f"sqlite:///{DB_PATH}"
