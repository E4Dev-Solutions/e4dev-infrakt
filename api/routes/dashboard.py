"""Dashboard stats API route."""

from fastapi import APIRouter

from api.schemas import DashboardStats, DeploymentOut
from cli.core.database import get_session, init_db
from cli.models.app import App
from cli.models.deployment import Deployment
from cli.models.server import Server

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=DashboardStats)
def dashboard_stats():
    init_db()
    with get_session() as session:
        total_servers = session.query(Server).count()
        active_servers = session.query(Server).filter(Server.status == "active").count()
        total_apps = session.query(App).filter(~App.app_type.like("db:%")).count()
        running_apps = session.query(App).filter(App.status == "running", ~App.app_type.like("db:%")).count()
        total_databases = session.query(App).filter(App.app_type.like("db:%")).count()

        recent_deps = (
            session.query(Deployment)
            .order_by(Deployment.started_at.desc())
            .limit(10)
            .all()
        )
        deployments = [DeploymentOut.model_validate(d) for d in recent_deps]

    return DashboardStats(
        total_servers=total_servers,
        active_servers=active_servers,
        total_apps=total_apps,
        running_apps=running_apps,
        total_databases=total_databases,
        recent_deployments=deployments,
    )
