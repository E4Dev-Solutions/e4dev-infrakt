"""FastAPI application — web API layer for infrakt."""

from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from api.auth import require_api_key
from api.routes import apps, dashboard, databases, deploy, env, keys, proxy, servers, webhooks
from cli.core.database import init_db

app = FastAPI(
    title="infrakt",
    description="Self-hosted PaaS API for multi-server, multi-app deployments",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes — all require API key authentication
api_deps = [Depends(require_api_key)]
app.include_router(dashboard.router, prefix="/api", dependencies=api_deps)
app.include_router(servers.router, prefix="/api", dependencies=api_deps)
app.include_router(apps.router, prefix="/api", dependencies=api_deps)
app.include_router(env.router, prefix="/api", dependencies=api_deps)
app.include_router(databases.router, prefix="/api", dependencies=api_deps)
app.include_router(proxy.router, prefix="/api", dependencies=api_deps)
app.include_router(webhooks.router, prefix="/api", dependencies=api_deps)
app.include_router(keys.router, prefix="/api", dependencies=api_deps)
app.include_router(deploy.router, prefix="/api")  # uses own auth dependency

# Serve built frontend in production
FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
