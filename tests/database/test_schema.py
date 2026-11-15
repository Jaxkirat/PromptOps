"""Schema shape, foreign keys and a non-destructive upgrade of an old SQLite file."""

import sqlite3
import shutil
from pathlib import Path

from sqlalchemy import text

from codeforge.config.settings import get_settings
from codeforge.database.database import get_engine, init_db, reset_database_state, session_scope
from codeforge.database.models import Conversation, Message, Run, Ticket, TicketMessage, User


def test_fresh_database_has_lightweight_tables_indexes_and_foreign_keys(tmp_path, monkeypatch):
    database = tmp_path / "fresh.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database.as_posix()}")
    get_settings.cache_clear()
    reset_database_state()
    init_db()
    engine = get_engine()
    with engine.connect() as connection:
        foreign_keys = connection.execute(text("PRAGMA foreign_keys")).scalar()
        tables = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        run_indexes = {
            row[1] for row in connection.execute(text("PRAGMA index_list(runs)"))
        }
        ticket_indexes = {
            row[1] for row in connection.execute(text("PRAGMA index_list(tickets)"))
        }
    assert foreign_keys == 1
    assert {
        "users",
        "conversations",
        "messages",
        "runs",
        "tickets",
        "ticket_messages",
        "run_feedback",
        "sql_query_audits",
    } <= tables
    assert "ix_runs_user_created" in run_indexes
    assert "ix_tickets_instructor_status" in ticket_indexes
    assert "ix_tickets_student_status" in ticket_indexes
    with session_scope() as session:
        columns = {column.name for column in Run.__table__.columns}
    assert {"conversation_id", "sanitised_request", "status", "completed_at"} <= columns
    assert "prompt" not in columns
    assert "password_hash" in {column.name for column in User.__table__.columns}


def test_migration_keeps_existing_rows(tmp_path, monkeypatch):
    database = tmp_path / "legacy.db"
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE users (
            id VARCHAR(32) PRIMARY KEY,
            email VARCHAR(320) NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(255) NOT NULL,
            role VARCHAR(20) NOT NULL,
            is_active BOOLEAN NOT NULL,
            created_at DATETIME,
            updated_at DATETIME
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE runs (
            id VARCHAR(32) PRIMARY KEY,
            user_id VARCHAR(32) NOT NULL,
            sanitised_request TEXT NOT NULL,
            task_type VARCHAR(20),
            language VARCHAR(50),
            status VARCHAR(30) NOT NULL,
            generated_code TEXT,
            generated_tests TEXT,
            test_results TEXT,
            execution_time FLOAT,
            redaction_count INTEGER NOT NULL,
            created_at DATETIME,
            artifacts_json TEXT
        )
        """
    )
    connection.execute(
        "INSERT INTO users VALUES ('user-kept', 'kept@example.com', 'hash', 'Kept Row', 'student', 1, '2026-01-01', '2026-01-01')"
    )
    connection.execute(
        "INSERT INTO runs VALUES ('run-kept', 'user-kept', 'keep this prompt', 'python', 'python', 'success', 'def kept():\n    return 1\n', '', '', 0.2, 0, '2026-01-01', NULL)"
    )
    connection.commit()
    connection.close()

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database.as_posix()}")
    get_settings.cache_clear()
    reset_database_state()
    init_db()
    with session_scope() as session:
        user = session.get(User, "user-kept")
        run = session.get(Run, "run-kept")
        assert user is not None and user.email == "kept@example.com"
        assert run is not None
        assert run.sanitised_request == "keep this prompt"
        assert run.generated_code.startswith("def kept")
        assert run.conversation_id is None
        assert session.query(Conversation).count() == 0
        assert session.query(Message).count() == 0
        assert session.query(Ticket).count() == 0
        assert session.query(TicketMessage).count() == 0


def test_development_database_copy_survives_migration(tmp_path, monkeypatch):
    source = Path("codeforge.db")
    if not source.exists():
        return
    target = tmp_path / "codeforge-copy.db"
    shutil.copy2(source, target)
    before = sqlite3.connect(target)
    user_count = before.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    run_count = before.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    before.close()
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{target.as_posix()}")
    get_settings.cache_clear()
    reset_database_state()
    init_db()
    after = sqlite3.connect(target)
    assert after.execute("SELECT COUNT(*) FROM users").fetchone()[0] == user_count
    assert after.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == run_count
    columns = {row[1] for row in after.execute("PRAGMA table_info(runs)")}
    tables = {row[0] for row in after.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    after.close()
    assert "conversation_id" in columns
    assert "completed_at" in columns
    assert {"conversations", "messages", "tickets", "ticket_messages"} <= tables
