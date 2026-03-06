"""Auto-domain generation for apps without explicit domains."""
from __future__ import annotations

import secrets

from cli.core.database import get_session, init_db
from cli.models.platform_settings import PlatformSettings


def generate_auto_domain(base_domain: str) -> str:
    """Generate a random subdomain like ``a3f2b7c1.infrakt.cloud``."""
    return f"{secrets.token_hex(4)}.{base_domain}"


def get_base_domain() -> str | None:
    """Read the configured base_domain from platform settings, or None."""
    init_db()
    with get_session() as session:
        ps = session.query(PlatformSettings).first()
        if ps and ps.base_domain:
            return ps.base_domain
    return None
