"""App templates API route."""

from __future__ import annotations

from fastapi import APIRouter

from cli.core.app_templates import list_templates

router = APIRouter(prefix="/templates", tags=["templates"])


@router.get("")
def get_templates() -> list[dict]:
    """List all available app templates."""
    return [
        {
            "name": t["name"],
            "description": t["description"],
            "services": t["services"],
            "port": t["port"],
            "domains": t.get("domains", 1),
        }
        for t in list_templates()
    ]
