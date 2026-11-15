"""Database engine and session management.

The engine is created lazily from ``Settings.database_url`` so tests can point
``DATABASE_URL`` at a temporary SQLite file and call
:func:`reset_database_state`. Access is kept behind SQLAlchemy so a future
PostgreSQL migration only requires a URL change.
"""

from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from codeforge.config.settings import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


_lock = threading.Lock()
_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def get_engine() -> Engine:
    """Return the lazily-created singleton engine."""
    global _engine, _session_factory
    with _lock:
        if _engine is None:
            url = get_settings().database_url
            connect_args = {}
            if url.startswith("sqlite"):
                # Allow FastAPI threadpool + background use; serialise writes politely.
                connect_args = {"check_same_thread": False, "timeout": 30}
            _engine = create_engine(url, connect_args=connect_args)
            _session_factory = sessionmaker(bind=_engine, expire_on_commit=False)
            logger.info("Database engine initialised (dialect=%s)", _engine.dialect.name)
        return _engine


def get_session_factory() -> sessionmaker[Session]:
    get_engine()
    assert _session_factory is not None
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Provide a transactional session scope (commit on success, rollback on error)."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db() -> None:
    """Create all tables (idempotent)."""
    import codeforge.database.models  # noqa: F401 - register models on Base

    Base.metadata.create_all(get_engine())


def reset_database_state() -> None:
    """Dispose the engine so the next access re-reads settings (used by tests)."""
    global _engine, _session_factory
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None
