"""Database engine and session management.

The engine is created lazily from ``Settings.database_url`` so tests can point
``DATABASE_URL`` at a temporary SQLite file and call
:func:`reset_database_state`. Access is kept behind SQLAlchemy so a future
PostgreSQL migration only requires a URL change.
"""

from __future__ import annotations

import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from codeforge.config.settings import get_settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, connection_record) -> None:
    """SQLite ignores foreign keys unless each connection turns them on."""
    del connection_record
    if isinstance(dbapi_connection, sqlite3.Connection):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


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
    """Create all tables (idempotent) and apply lightweight SQLite column adds."""
    import codeforge.database.models  # noqa: F401 - register models on Base

    engine = get_engine()
    from codeforge.database.migrate import apply_schema_updates, backup_development_database

    backup_development_database(engine)
    Base.metadata.create_all(engine)
    apply_schema_updates(engine)
    _ensure_sqlite_columns(engine)


def _ensure_sqlite_columns(engine: Engine) -> None:
    """Add columns introduced after the initial schema without a full migrator."""
    if engine.dialect.name != "sqlite":
        return
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "runs" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("runs")}
    if "artifacts_json" not in existing:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE runs ADD COLUMN artifacts_json TEXT"))


def reset_database_state() -> None:
    """Dispose the engine so the next access re-reads settings (used by tests)."""
    global _engine, _session_factory
    with _lock:
        if _engine is not None:
            _engine.dispose()
        _engine = None
        _session_factory = None
