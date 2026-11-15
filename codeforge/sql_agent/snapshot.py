"""Copy only the rows a scope may see into a temporary SQLite file.

Unauthorized students are not present in the file, so a UNION or subquery cannot
select them. ``user_id``, email, and credentials are not columns of these tables.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from codeforge.database.database import session_scope
from codeforge.database.models import Run
from codeforge.privacy.masker import mask_sensitive_data
from codeforge.sql_agent.allowlist import CELL_CHAR_CAP, COLUMNS, SAMPLE_TABLES, SNAPSHOT_ROW_CAP
from codeforge.sql_agent.models import AccessScope, TicketGrant
from codeforge.sql_agent.sample_db import ensure_sample_database
from codeforge.sql_agent.tickets import get_ticket_access


def _clip(value: object) -> str:
    text = "" if value is None else str(value)
    masked = mask_sensitive_data(text).sanitized_text
    if len(masked) > CELL_CHAR_CAP:
        return masked[:CELL_CHAR_CAP]
    return masked


def _stamp(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat()


def _json_dict(raw: str | None) -> dict:
    if not raw:
        return {}
    try:
        loaded = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def load_scoped_runs(scope: AccessScope) -> list[Run]:
    """Read runs with the application ORM. The model SQL is not used here."""
    if scope.mode == "sample_only" or not scope.run_ids or not scope.owner_user_id:
        return []
    with session_scope() as session:
        rows = (
            session.query(Run)
            .filter(Run.user_id == scope.owner_user_id, Run.id.in_(scope.run_ids))
            .order_by(Run.created_at.desc())
            .limit(SNAPSHOT_ROW_CAP)
            .all()
        )
        session.expunge_all()
        return rows


def _execution_cells(run: Run) -> tuple:
    artifacts = _json_dict(run.artifacts_json)
    tests = run.test_results if isinstance(run.test_results, dict) else _json_dict(run.test_results)
    tests_passed = 1 if artifacts.get("tests_passed") is True or tests.get("passed") and not tests.get("failed") else 0
    if artifacts.get("tests_passed") is False:
        tests_passed = 0
    policy = _clip(artifacts.get("policy_decision") or "")
    error = _clip(artifacts.get("error_message") or tests.get("stderr") or "")
    return (
        run.id,
        _stamp(run.created_at),
        _clip(run.status),
        tests_passed,
        policy,
        error,
        run.execution_time if run.execution_time is not None else None,
    )


def _create_table(connection: sqlite3.Connection, name: str) -> None:
    numeric = {"execution_time", "tests_passed", "amount", "id", "employee_id"}
    parts = [
        f"{column} {'REAL' if column in numeric else 'TEXT'}" for column in COLUMNS[name]
    ]
    connection.execute(f"CREATE TABLE {name} ({', '.join(parts)})")


def _user_message_ids(run_ids: list[str]) -> dict[str, str]:
    if not run_ids:
        return {}
    from codeforge.database.models import Message

    with session_scope() as session:
        rows = (
            session.query(Message.run_id, Message.id)
            .filter(Message.run_id.in_(run_ids), Message.role == "user")
            .all()
        )
    return {run_id: message_id for run_id, message_id in rows if run_id}


def _insert_runs(connection: sqlite3.Connection, tables: set[str], runs: list[Run]) -> None:
    for name in sorted(tables):
        if name.startswith("student_"):
            _create_table(connection, name)
    message_ids = _user_message_ids([run.id for run in runs])
    for run in runs:
        if "student_run_history" in tables:
            connection.execute(
                "INSERT INTO student_run_history VALUES (?, ?, ?, ?, ?, ?)",
                (
                    run.id,
                    _stamp(run.created_at),
                    _clip(run.task_type),
                    _clip(run.language),
                    _clip(run.status),
                    run.execution_time,
                ),
            )
        if "student_prompt_history" in tables:
            connection.execute(
                "INSERT INTO student_prompt_history VALUES (?, ?, ?, ?, ?)",
                (
                    run.id,
                    run.conversation_id or "",
                    message_ids.get(run.id, ""),
                    _stamp(run.created_at),
                    _clip(run.sanitised_request),
                ),
            )
        if "student_generated_code" in tables:
            connection.execute(
                "INSERT INTO student_generated_code VALUES (?, ?, ?, ?)",
                (
                    run.id,
                    _stamp(run.created_at),
                    _clip(run.generated_code),
                    _clip(run.generated_tests),
                ),
            )
        if "student_execution_results" in tables:
            connection.execute(
                "INSERT INTO student_execution_results VALUES (?, ?, ?, ?, ?, ?, ?)",
                _execution_cells(run),
            )


def _active_grant(scope: AccessScope) -> TicketGrant | None:
    if scope.mode != "instructor_ticket" or not scope.ticket_id:
        return None
    for grant in get_ticket_access().grants_for_instructor(scope.principal_id):
        if grant.ticket_id == scope.ticket_id:
            return grant
    return None


def _insert_tickets(connection: sqlite3.Connection, tables: set[str], scope: AccessScope, runs: list[Run]) -> None:
    grant = _active_grant(scope)
    if grant is None:
        return
    if "ticket_handoff_context" in tables:
        _create_table(connection, "ticket_handoff_context")
        primary = runs[0].id if runs else ""
        connection.execute(
            "INSERT INTO ticket_handoff_context VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                grant.ticket_id,
                _clip(grant.priority),
                _clip(grant.created_at),
                _clip(grant.sla_status),
                grant.student_ref,
                _clip(grant.sanitised_request),
                _clip(grant.handoff_summary),
                str(grant.attempts),
                _clip(grant.last_failing_test),
                primary,
            ),
        )
    if "ticket_repair_history" in tables:
        _create_table(connection, "ticket_repair_history")
        ordered = list(reversed(runs))
        for run in ordered:
            _run_id, created, status, tests_passed, policy, error, _time = _execution_cells(run)
            connection.execute(
                "INSERT INTO ticket_repair_history VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    grant.ticket_id,
                    run.id,
                    created,
                    status,
                    _clip(run.generated_code),
                    policy,
                    tests_passed,
                    error,
                ),
            )


def _insert_sample(connection: sqlite3.Connection, tables: set[str]) -> None:
    wanted = tables & set(SAMPLE_TABLES)
    if not wanted:
        return
    source_path = ensure_sample_database()
    source = sqlite3.connect(f"{source_path.resolve().as_uri()}?mode=ro", uri=True)
    try:
        if "employees" in wanted:
            _create_table(connection, "employees")
            rows = source.execute("SELECT id, employee_code, department FROM employees").fetchall()
            connection.executemany("INSERT INTO employees VALUES (?, ?, ?)", rows)
        if "sales" in wanted:
            _create_table(connection, "sales")
            rows = source.execute(
                "SELECT id, employee_id, amount, region, sold_on FROM sales"
            ).fetchall()
            connection.executemany("INSERT INTO sales VALUES (?, ?, ?, ?, ?)", rows)
    finally:
        source.close()


def build_snapshot(path: Path, scope: AccessScope, tables: tuple[str, ...]) -> None:
    """Create ``path`` containing only ``tables`` and only in-scope rows."""
    requested = set(tables)
    connection = sqlite3.connect(path)
    try:
        runs = load_scoped_runs(scope) if requested & set(COLUMNS) - SAMPLE_TABLES else []
        _insert_runs(connection, requested, runs)
        _insert_tickets(connection, requested, scope, runs)
        _insert_sample(connection, requested)
        connection.commit()
    finally:
        connection.close()
