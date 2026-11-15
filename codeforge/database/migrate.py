"""Add missing tables, columns and indexes without dropping existing rows.

``create_all`` creates brand-new tables. It does not alter a table that already
exists, so older SQLite files receive explicit ``ALTER TABLE`` and
``CREATE INDEX IF NOT EXISTS`` statements.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def backup_development_database(engine: Engine) -> Path | None:
    """Copy ``codeforge.db`` once, before the first schema update."""
    if engine.dialect.name != "sqlite":
        return None
    database = engine.url.database
    if not database or database == ":memory:":
        return None
    path = Path(database)
    if path.name != "codeforge.db" or not path.exists() or path.stat().st_size == 0:
        return None
    backup = path.with_name("codeforge.db.pre-schema.bak")
    if backup.exists():
        return backup
    shutil.copy2(path, backup)
    return backup


def _ensure_ticket_columns(connection, inspector) -> None:
    """Add the SLA column and allow an unassigned ticket when no instructor exists."""
    columns = {column["name"]: column for column in inspector.get_columns("tickets")}
    if "sla_due_at" not in columns:
        connection.execute(text("ALTER TABLE tickets ADD COLUMN sla_due_at DATETIME"))
    instructor = columns.get("instructor_id")
    if instructor is None or instructor.get("nullable", True):
        return
    connection.execute(text("ALTER TABLE tickets RENAME TO tickets_pre_r3"))
    connection.execute(
        text(
            """
            CREATE TABLE tickets (
                id VARCHAR(32) PRIMARY KEY,
                student_id VARCHAR(32) NOT NULL,
                instructor_id VARCHAR(32),
                run_id VARCHAR(32),
                priority VARCHAR(20) NOT NULL,
                status VARCHAR(20) NOT NULL,
                trigger_reason TEXT NOT NULL,
                handoff_note TEXT NOT NULL,
                last_failing_test TEXT NOT NULL,
                created_at DATETIME,
                sla_due_at DATETIME,
                first_response_at DATETIME,
                resolved_at DATETIME,
                FOREIGN KEY(student_id) REFERENCES users(id),
                FOREIGN KEY(instructor_id) REFERENCES users(id),
                FOREIGN KEY(run_id) REFERENCES runs(id)
            )
            """
        )
    )
    connection.execute(
        text(
            """
            INSERT INTO tickets (
                id, student_id, instructor_id, run_id, priority, status, trigger_reason,
                handoff_note, last_failing_test, created_at, first_response_at, resolved_at
            )
            SELECT id, student_id, instructor_id, run_id, priority, status, trigger_reason,
                   handoff_note, last_failing_test, created_at, first_response_at, resolved_at
            FROM tickets_pre_r3
            """
        )
    )
    connection.execute(text("DROP TABLE tickets_pre_r3"))


def apply_schema_updates(engine: Engine) -> None:
    """Bring an existing SQLite file up to the current lightweight schema."""
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    with engine.begin() as connection:
        if "runs" in tables:
            columns = {column["name"] for column in inspector.get_columns("runs")}
            if "artifacts_json" not in columns:
                connection.execute(text("ALTER TABLE runs ADD COLUMN artifacts_json TEXT"))
            if "conversation_id" not in columns:
                connection.execute(text("ALTER TABLE runs ADD COLUMN conversation_id VARCHAR(32)"))
            if "completed_at" not in columns:
                connection.execute(text("ALTER TABLE runs ADD COLUMN completed_at DATETIME"))
            if "llm_usage_json" not in columns:
                connection.execute(text("ALTER TABLE runs ADD COLUMN llm_usage_json TEXT"))
        if "conversations" in tables:
            conversation_columns = {column["name"] for column in inspector.get_columns("conversations")}
            if "escalation_state_json" not in conversation_columns:
                connection.execute(
                    text("ALTER TABLE conversations ADD COLUMN escalation_state_json TEXT NOT NULL DEFAULT '{}'")
                )
        if "tickets" in tables:
            _ensure_ticket_columns(connection, inspector)
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_runs_user_created ON runs (user_id, created_at)")
        )
        if "conversations" in inspector.get_table_names() or "conversations" in tables:
            connection.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_conversations_user_created "
                    "ON conversations (user_id, created_at)"
                )
            )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_messages_conversation_created "
                "ON messages (conversation_id, created_at)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_tickets_student_status ON tickets (student_id, status)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_tickets_instructor_status "
                "ON tickets (instructor_id, status)"
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_ticket_messages_ticket_created "
                "ON ticket_messages (ticket_id, created_at)"
            )
        )
