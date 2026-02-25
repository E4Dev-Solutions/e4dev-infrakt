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
    ]
    with engine.connect() as conn:
        for sql in migrations:
            try:
                conn.execute(text(sql))
                conn.commit()
            except OperationalError:
                conn.rollback()


def init_db() -> None:
    """Create all tables."""
    # Import models so they register with Base metadata
    import cli.models  # noqa: F401

    engine = _get_engine()
    Base.metadata.create_all(engine)
    _apply_migrations(engine)


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
