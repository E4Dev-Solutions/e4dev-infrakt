"""Platform settings API routes (S3 backup storage, backup policy, etc.)."""

import logging

from fastapi import APIRouter, HTTPException

from api.helpers import get_s3_config as _get_s3_config
from api.schemas import BackupPolicySave, S3ConfigSave
from cli.core.backup import install_backup_cron, remove_backup_cron
from cli.core.crypto import encrypt
from cli.core.database import get_session, init_db
from cli.core.ssh import SSHClient
from cli.models.app import App
from cli.models.backup_policy import BackupPolicy
from cli.models.s3_config import S3Config
from cli.models.server import Server

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("/s3")
def get_s3_settings() -> dict:
    init_db()
    with get_session() as session:
        cfg = session.query(S3Config).first()
        if not cfg:
            return {"configured": False}
        return {
            "configured": True,
            "endpoint_url": cfg.endpoint_url,
            "bucket": cfg.bucket,
            "region": cfg.region,
            "access_key": cfg.access_key,
            "prefix": cfg.prefix,
        }


@router.put("/s3")
def save_s3_config(body: S3ConfigSave) -> dict[str, str]:
    init_db()
    with get_session() as session:
        cfg = session.query(S3Config).first()
        if cfg:
            cfg.endpoint_url = body.endpoint_url
            cfg.bucket = body.bucket
            cfg.region = body.region
            cfg.access_key = body.access_key
            cfg.secret_key_encrypted = encrypt(body.secret_key)
            cfg.prefix = body.prefix
        else:
            cfg = S3Config(
                endpoint_url=body.endpoint_url,
                bucket=body.bucket,
                region=body.region,
                access_key=body.access_key,
                secret_key_encrypted=encrypt(body.secret_key),
                prefix=body.prefix,
            )
            session.add(cfg)
    return {"message": "S3 configuration saved"}


@router.delete("/s3")
def delete_s3_config() -> dict[str, str]:
    init_db()
    with get_session() as session:
        cfg = session.query(S3Config).first()
        if cfg:
            session.delete(cfg)
    return {"message": "S3 configuration removed"}


# ── Backup Policy ──────────────────────────────────────────────────────────


@router.get("/backup-policy")
def get_backup_policy() -> dict:
    init_db()
    with get_session() as session:
        policy = session.query(BackupPolicy).first()
        total = session.query(App).filter(App.app_type.like("db:%")).count()
        scheduled = (
            session.query(App)
            .filter(App.app_type.like("db:%"), App.backup_schedule.isnot(None))
            .count()
        )
        if not policy:
            return {
                "default_cron": None,
                "default_retention_days": 7,
                "s3_max_backups_per_db": 10,
                "s3_max_age_days": 30,
                "scheduled_count": scheduled,
                "total_count": total,
            }
        return {
            "default_cron": policy.default_cron,
            "default_retention_days": policy.default_retention_days,
            "s3_max_backups_per_db": policy.s3_max_backups_per_db,
            "s3_max_age_days": policy.s3_max_age_days,
            "scheduled_count": scheduled,
            "total_count": total,
        }


@router.put("/backup-policy")
def save_backup_policy(body: BackupPolicySave) -> dict[str, str]:
    init_db()
    with get_session() as session:
        policy = session.query(BackupPolicy).first()
        if policy:
            policy.default_cron = body.default_cron
            policy.default_retention_days = body.default_retention_days
            policy.s3_max_backups_per_db = body.s3_max_backups_per_db
            policy.s3_max_age_days = body.s3_max_age_days
        else:
            session.add(
                BackupPolicy(
                    default_cron=body.default_cron,
                    default_retention_days=body.default_retention_days,
                    s3_max_backups_per_db=body.s3_max_backups_per_db,
                    s3_max_age_days=body.s3_max_age_days,
                )
            )
    return {"message": "Backup policy saved"}


@router.post("/backup-policy/apply-all")
def apply_backup_policy_all() -> dict:
    """Install backup cron on all unscheduled databases using policy defaults."""
    init_db()
    with get_session() as session:
        policy = session.query(BackupPolicy).first()
        if not policy or not policy.default_cron:
            raise HTTPException(400, "Set a default cron expression before applying")
        cron = policy.default_cron
        retention = policy.default_retention_days

    s3_cfg = _get_s3_config()
    applied = 0

    with get_session() as session:
        db_apps = (
            session.query(App)
            .filter(App.app_type.like("db:%"), App.backup_schedule.is_(None))
            .all()
        )
        # Collect info and detach from session
        targets = []
        for db_app in db_apps:
            srv = session.query(Server).filter(Server.id == db_app.server_id).first()
            if not srv:
                continue
            session.refresh(db_app)
            session.expunge(db_app)
            targets.append((db_app, SSHClient.from_server(srv), srv.name, db_app.id))

    for db_app, ssh, server_name, app_id in targets:
        try:
            with ssh:
                install_backup_cron(
                    ssh,
                    db_app,
                    cron,
                    retention,
                    s3_endpoint=s3_cfg["endpoint_url"] if s3_cfg else None,
                    s3_bucket=s3_cfg["bucket"] if s3_cfg else None,
                    s3_region=s3_cfg["region"] if s3_cfg else None,
                    s3_access_key=s3_cfg["access_key"] if s3_cfg else None,
                    s3_secret_key=s3_cfg["secret_key"] if s3_cfg else None,
                    s3_prefix=s3_cfg.get("prefix", "") if s3_cfg else "",
                    server_name=server_name,
                )
            with get_session() as session:
                a = session.query(App).filter(App.id == app_id).first()
                if a:
                    a.backup_schedule = cron
            applied += 1
        except Exception:
            logger.warning("Failed to apply schedule to %s", db_app.name, exc_info=True)

    return {
        "message": f"Applied backup schedule to {applied} database(s)",
        "count": applied,
    }


@router.post("/backup-policy/disable-all")
def disable_all_backup_schedules() -> dict:
    """Remove backup cron from all scheduled databases."""
    init_db()
    removed = 0

    with get_session() as session:
        db_apps = (
            session.query(App)
            .filter(
                App.app_type.like("db:%"),
                App.backup_schedule.isnot(None),
            )
            .all()
        )
        targets = []
        for db_app in db_apps:
            srv = session.query(Server).filter(Server.id == db_app.server_id).first()
            if not srv:
                continue
            session.refresh(db_app)
            session.expunge(db_app)
            targets.append((db_app, SSHClient.from_server(srv), db_app.id))

    for db_app, ssh, app_id in targets:
        try:
            with ssh:
                remove_backup_cron(ssh, db_app)
            with get_session() as session:
                a = session.query(App).filter(App.id == app_id).first()
                if a:
                    a.backup_schedule = None
            removed += 1
        except Exception:
            logger.warning(
                "Failed to remove schedule from %s",
                db_app.name,
                exc_info=True,
            )

    return {
        "message": f"Disabled backup schedules for {removed} database(s)",
        "count": removed,
    }
