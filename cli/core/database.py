from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from cli.core.config import ensure_config_dir, get_db_url


class Base(DeclarativeBase):
    pass


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def _get_engine() -> Engine:
    global _engine
    if _engine is None:
        ensure_config_dir()
        _engine = create_engine(get_db_url(), echo=False)
    return _engine


def _get_session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=_get_engine())
    return _SessionLocal


def _apply_migrations(engine: Engine) -> None:
    """Apply incremental schema migrations for existing databases."""
    migrations = [
        "ALTER TABLE deployments ADD COLUMN image_used VARCHAR(500)",
        "ALTER TABLE apps ADD COLUMN backup_schedule VARCHAR(100)",
        "ALTER TABLE apps ADD COLUMN cpu_limit VARCHAR(20)",
        "ALTER TABLE apps ADD COLUMN memory_limit VARCHAR(20)",
        "ALTER TABLE apps ADD COLUMN health_check_url VARCHAR(500)",
        "ALTER TABLE apps ADD COLUMN health_check_interval INTEGER",
        "ALTER TABLE apps ADD COLUMN replicas INTEGER DEFAULT 1",
        "ALTER TABLE apps ADD COLUMN deploy_strategy VARCHAR(20) DEFAULT 'restart'",
        "ALTER TABLE apps ADD COLUMN webhook_secret VARCHAR(100)",
        "ALTER TABLE apps ADD COLUMN auto_deploy BOOLEAN DEFAULT 1",
        "ALTER TABLE apps ADD COLUMN parent_app_id INTEGER REFERENCES apps(id) ON DELETE CASCADE",
        "ALTER TABLE servers ADD COLUMN is_infrakt_host BOOLEAN DEFAULT 0",
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except OperationalError:
                conn.rollback()


def _backfill_template_dbs() -> None:
    """Create child DB records for existing template apps that lack them."""
    from cli.commands.db import DB_TEMPLATES
    from cli.core.app_templates import APP_TEMPLATES
    from cli.models.app import App

    session = _get_session_factory()()
    try:
        template_apps = session.query(App).filter(App.app_type.like("template:%")).all()
        for app in template_apps:
            tmpl_name = app.app_type.split(":", 1)[1]
            tmpl = APP_TEMPLATES.get(tmpl_name)
            if not tmpl:
                continue
            db_services: dict[str, str] = tmpl.get("db_services", {})
            if not db_services:
                continue
            # Skip if child records already exist
            existing = session.query(App).filter(App.parent_app_id == app.id).count()
            if existing:
                continue
            for suffix, db_type in db_services.items():
                db_port = DB_TEMPLATES.get(db_type, {}).get("port", 0)
                child_name = f"{app.name}-{suffix}"
                # Avoid duplicates by name+server
                dup = (
                    session.query(App)
                    .filter(App.name == child_name, App.server_id == app.server_id)
                    .count()
                )
                if dup:
                    continue
                child = App(
                    name=child_name,
                    server_id=app.server_id,
                    port=db_port,
                    app_type=f"db:{db_type}",
                    status="running",
                    parent_app_id=app.id,
                )
                session.add(child)
        session.commit()
    except Exception:
        session.rollback()
    finally:
        session.close()


def init_db() -> None:
    """Create all tables."""
    # Import models so they register with Base metadata
    import cli.models  # noqa: F401

    engine = _get_engine()
    Base.metadata.create_all(engine)
    _apply_migrations(engine)
    _backfill_template_dbs()


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Yield a database session with automatic commit/rollback."""
    session = _get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
