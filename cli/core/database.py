from collections.abc import Generator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
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


def init_db() -> None:
    """Create all tables."""
    # Import models so they register with Base metadata
    import cli.models  # noqa: F401

    Base.metadata.create_all(_get_engine())


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
