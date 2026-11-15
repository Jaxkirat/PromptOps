"""Ask a question. Identity, scope, validation and execution stay in this module.

The proposer never sees the caller's user id. A successful summary is built from
the row count actually returned.
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

from codeforge.auth.identity import current_principal
from codeforge.config.settings import Settings, get_settings
from codeforge.database.database import session_scope
from codeforge.database.models import Run, SqlQueryAudit
from codeforge.exceptions import AuthorizationError, SqlAgentDisabledError, SqlTicketNotFoundError
from codeforge.privacy.masker import mask_sensitive_data
from codeforge.sql_agent.allowlist import (
    AUDIT_TEXT_CAP,
    MAX_PARAMETERS,
    SAMPLE_TABLES,
    STUDENT_TABLES,
    TICKET_TABLES,
    schema_text,
)
from codeforge.sql_agent.models import AccessScope, SqlAnswer, SqlProposal
from codeforge.sql_agent.proposer import get_sql_proposer, looks_like_sql
from codeforge.sql_agent.readonly import run_readonly
from codeforge.sql_agent.redact import redact_results
from codeforge.sql_agent.snapshot import build_snapshot, load_scoped_runs
from codeforge.sql_agent.tickets import get_ticket_access
from codeforge.sql_agent.validate import validate_sql

logger = logging.getLogger(__name__)

_CROSS_USER = re.compile(
    r"\b(all students|every student|other students?|another student|all users|every user|other users?)\b",
    re.IGNORECASE,
)
_SENSITIVE = re.compile(
    r"\b(passwords?|password_hash|jwts?|api[_ ]?keys?|aadhaar|secret keys?|phone numbers?|email addresses?)\b",
    re.IGNORECASE,
)
_ROLE_CLAIM = re.compile(r"\bi am an instructor\b", re.IGNORECASE)
_INJECTION = re.compile(
    r"ignore (all|any|previous|the) (instructions|rules)|bypass (the )?(scope|filter|authori[sz]ation)",
    re.IGNORECASE,
)
_HEX_ID = re.compile(r"\b[0-9a-fA-F]{32}\b")

_MESSAGES = {
    "write_statement": "Only a single read-only query is allowed.",
    "multiple_statements": "Only a single read-only query is allowed.",
    "attach": "Only a single read-only query is allowed.",
    "pragma": "Only a single read-only query is allowed.",
    "forbidden_table": "That query is outside the tables you can access.",
    "forbidden_function": "That query uses a function that is not allowed.",
    "malformed_sql": "The query could not be understood.",
    "limit_invalid": "The query limit is not valid.",
    "outside_scope": "That query is outside your access.",
    "mixed_schema": "Application history and the sample dataset cannot be queried together.",
    "cross_user": "You can only query your own CodeForge history.",
    "foreign_identifier": "That query is outside your access.",
    "role_claim": "You can only query your own CodeForge history.",
    "prompt_injection": "That query is outside your access.",
    "pii_request": "That question includes data this agent will not process.",
    "sensitive_request": "Credentials and personal data are not available through this agent.",
    "generation_failed": "A read-only query could not be prepared for that question.",
    "parameter_error": "The query parameters were rejected.",
    "setup_error": "The SQL agent is not configured. Install sqlglot and set CODEFORGE_SQL_DIALECT=sqlite.",
    "database_rejected": "The query could not be completed.",
    "execution_error": "The query could not be completed.",
    "timeout": "The query took too long and was stopped.",
    "too_many_columns": "The query returns too many columns.",
    "scope_violation": "The query result was discarded because it failed an access check.",
    "unassigned_ticket": "Ticket not found",
}


def _clip(text: str) -> str:
    masked = mask_sensitive_data(text or "").sanitized_text
    return masked[:AUDIT_TEXT_CAP]


def _identifiers(scope_ids: set[str], *extra: str | None) -> frozenset[str]:
    values = {item.lower() for item in scope_ids if item}
    for item in extra:
        if item:
            values.add(item.lower())
    return frozenset(values)


def resolve_scope(ticket_id: str | None) -> AccessScope:
    """Build the scope from the authenticated principal. Client ids are not accepted."""
    principal = current_principal()
    requested = (ticket_id or "").strip() or None
    if principal.role == "student":
        if requested:
            raise AuthorizationError("Students cannot query instructor tickets.")
        with session_scope() as session:
            rows = (
                session.query(Run.id)
                .filter(Run.user_id == principal.user_id)
                .all()
            )
        run_ids = tuple(row[0] for row in rows)
        return AccessScope(
            principal_id=principal.user_id,
            role=principal.role,
            mode="student_self",
            owner_user_id=principal.user_id,
            run_ids=run_ids,
            ticket_id=None,
            student_ref=None,
            allowed_tables=STUDENT_TABLES | SAMPLE_TABLES,
            allowed_identifiers=_identifiers(set(run_ids), principal.user_id),
        )
    if requested is None:
        return AccessScope(
            principal_id=principal.user_id,
            role=principal.role,
            mode="sample_only",
            owner_user_id=None,
            run_ids=(),
            ticket_id=None,
            student_ref=None,
            allowed_tables=SAMPLE_TABLES,
            allowed_identifiers=_identifiers(set(), principal.user_id),
        )
    grant = next(
        (
            item
            for item in get_ticket_access().grants_for_instructor(principal.user_id)
            if item.ticket_id == requested
        ),
        None,
    )
    if grant is None:
        raise SqlTicketNotFoundError()
    return AccessScope(
        principal_id=principal.user_id,
        role=principal.role,
        mode="instructor_ticket",
        owner_user_id=grant.student_id,
        run_ids=tuple(grant.run_ids),
        ticket_id=grant.ticket_id,
        student_ref=grant.student_ref,
        allowed_tables=STUDENT_TABLES | TICKET_TABLES | SAMPLE_TABLES,
        allowed_identifiers=_identifiers(
            set(grant.run_ids), principal.user_id, grant.ticket_id, grant.student_ref
        ),
    )


def question_violation(question: str, scope: AccessScope, redactions: int) -> str | None:
    if redactions:
        return "pii_request"
    if looks_like_sql(question):
        return None
    if _INJECTION.search(question):
        return "prompt_injection"
    if _SENSITIVE.search(question):
        return "sensitive_request"
    if _CROSS_USER.search(question):
        return "cross_user"
    if scope.role != "instructor" and _ROLE_CLAIM.search(question):
        return "role_claim"
    if scope.role != "instructor" and re.search(r"\bstudent\b", question, re.IGNORECASE):
        return "cross_user"
    found = {match.group(0).lower() for match in _HEX_ID.finditer(question)}
    if any(item not in scope.allowed_identifiers for item in found):
        return "foreign_identifier"
    return None


def authorize_tables(tables: tuple[str, ...], scope: AccessScope) -> str | None:
    names = set(tables)
    if not names <= scope.allowed_tables:
        return "outside_scope"
    application = names & (STUDENT_TABLES | TICKET_TABLES)
    if names & SAMPLE_TABLES and application:
        return "mixed_schema"
    if scope.mode == "sample_only" and application:
        return "outside_scope"
    if scope.mode == "student_self" and names & TICKET_TABLES:
        return "outside_scope"
    return None


def _check_parameters(proposal: SqlProposal) -> str | None:
    if len(proposal.parameters) > MAX_PARAMETERS:
        return "parameter_error"
    for value in proposal.parameters:
        if isinstance(value, (dict, list, tuple, bytes)):
            return "parameter_error"
        if not isinstance(value, (str, int, float, bool, type(None))):
            return "parameter_error"
        if isinstance(value, str) and len(value) > 500:
            return "parameter_error"
    placeholders = proposal.sql.count("?")
    if placeholders != len(proposal.parameters):
        return "parameter_error"
    return None


def _success_message(scope: AccessScope, count: int, limited: bool, *, sample: bool) -> str:
    if count == 0:
        message = "No matching records."
    elif sample or scope.mode == "sample_only":
        message = f"Returned {count} row(s) from the sample dataset."
    elif scope.mode == "student_self":
        message = f"Returned {count} row(s) from your CodeForge history."
    elif scope.mode == "instructor_ticket":
        message = f"Returned {count} row(s) for the assigned ticket."
    else:
        message = f"Returned {count} row(s)."
    if limited:
        message += " The result was limited to the configured maximum."
    return message


def _audit(
    *,
    user_id: str,
    role: str,
    mode: str,
    ticket_id: str | None,
    question: str,
    sql: str,
    outcome: str,
    row_count: int,
    duration_ms: int,
    category: str | None,
) -> None:
    with session_scope() as session:
        session.add(
            SqlQueryAudit(
                user_id=user_id,
                role=role,
                access_mode=mode,
                ticket_id=ticket_id,
                sanitised_question=_clip(question),
                validated_sql=_clip(sql),
                outcome=outcome,
                row_count=row_count,
                duration_ms=duration_ms,
                rejection_category=category,
            )
        )


def _answer(
    *,
    ok: bool,
    category: str | None,
    scope: AccessScope,
    columns: list[str] | None = None,
    rows: list[list[Any]] | None = None,
    truncated: bool = False,
    executed: bool = False,
    validated_sql: str | None = None,
    limit_applied: int | None = None,
    clamped: bool = False,
    sample: bool = False,
) -> SqlAnswer:
    materialised = rows or []
    if ok:
        message = _success_message(scope, len(materialised), truncated or clamped, sample=sample)
    else:
        message = _MESSAGES.get(category or "", "The query could not be completed.")
    visible_sql = (
        mask_sensitive_data(validated_sql).sanitized_text
        if scope.role == "instructor" and ok and validated_sql
        else None
    )
    return SqlAnswer(
        ok=ok,
        message=message,
        columns=columns or [],
        rows=materialised if ok else [],
        row_count=len(materialised) if ok else 0,
        truncated=truncated if ok else False,
        rejection_category=None if ok else category,
        validated_sql=visible_sql,
        limit_applied=limit_applied if ok else None,
        clamped=clamped if ok else False,
        executed=executed if ok else False,
        access_mode=scope.mode,
        ticket_id=scope.ticket_id,
    )


def ask_sql(question: str, ticket_id: str | None = None) -> SqlAnswer:
    settings = get_settings()
    if not settings.sql_agent_enabled:
        raise SqlAgentDisabledError(
            "The SQL agent is disabled. Set CODEFORGE_SQL_AGENT_ENABLED=true to use it."
        )
    principal = current_principal()
    started = time.perf_counter()
    masked = mask_sensitive_data(question or "")
    try:
        scope = resolve_scope(ticket_id)
    except SqlTicketNotFoundError:
        _audit(
            user_id=principal.user_id,
            role=principal.role,
            mode="instructor_ticket",
            ticket_id=(ticket_id or "")[:64] or None,
            question=masked.sanitized_text,
            sql="",
            outcome="rejected",
            row_count=0,
            duration_ms=_elapsed(started),
            category="unassigned_ticket",
        )
        raise
    violation = question_violation(masked.sanitized_text, scope, masked.redaction_count)
    if violation:
        return _reject(settings, principal, scope, masked.sanitized_text, "", violation, started)
    proposal = get_sql_proposer().propose(
        masked.sanitized_text,
        schema_text(scope.allowed_tables),
        scope.mode,
    )
    if proposal is None or not proposal.sql.strip():
        return _reject(
            settings, principal, scope, masked.sanitized_text, "", "generation_failed", started
        )
    validation = validate_sql(
        proposal.sql,
        max_limit=settings.sql_max_rows,
        default_limit=min(settings.sql_default_limit, settings.sql_max_rows),
        dialect=settings.sql_dialect,
    )
    if not validation.ok:
        return _reject(
            settings,
            principal,
            scope,
            masked.sanitized_text,
            proposal.sql,
            validation.category,
            started,
        )
    table_problem = authorize_tables(validation.tables, scope)
    if table_problem:
        return _reject(
            settings,
            principal,
            scope,
            masked.sanitized_text,
            validation.sql,
            table_problem,
            started,
        )
    proposal = proposal.model_copy(update={"sql": validation.sql})
    parameter_problem = _check_parameters(proposal)
    if parameter_problem:
        return _reject(
            settings,
            principal,
            scope,
            masked.sanitized_text,
            validation.sql,
            parameter_problem,
            started,
        )
    import tempfile
    from pathlib import Path

    try:
        with tempfile.TemporaryDirectory(prefix="cf_sql_") as tmp:
            path = Path(tmp) / "snapshot.sqlite"
            build_snapshot(path, scope, validation.tables)
            result = run_readonly(
                path,
                validation.sql,
                list(proposal.parameters),
                timeout_seconds=settings.sql_timeout_seconds,
                max_rows=settings.sql_max_rows,
                max_bytes=settings.sql_max_result_bytes,
                max_columns=settings.sql_max_columns,
            )
    except Exception:
        logger.error("sql_snapshot_failed category=execution_error")
        return _reject(
            settings, principal, scope, masked.sanitized_text, validation.sql, "execution_error", started
        )
    if not result.ok:
        return _reject(
            settings,
            principal,
            scope,
            masked.sanitized_text,
            validation.sql,
            result.category or "database_rejected",
            started,
        )
    enforce_runs = bool(set(validation.tables) & (STUDENT_TABLES | TICKET_TABLES))
    redacted = redact_results(result, scope, enforce_runs=enforce_runs)
    if not redacted.ok:
        return _reject(
            settings,
            principal,
            scope,
            masked.sanitized_text,
            validation.sql,
            redacted.category or "scope_violation",
            started,
        )
    answer = _answer(
        ok=True,
        category=None,
        scope=scope,
        columns=redacted.columns,
        rows=redacted.rows,
        truncated=redacted.truncated,
        executed=True,
        validated_sql=validation.sql,
        limit_applied=validation.limit_applied,
        clamped=validation.clamped,
        sample=bool(validation.tables) and set(validation.tables) <= SAMPLE_TABLES,
    )
    _audit(
        user_id=principal.user_id,
        role=principal.role,
        mode=scope.mode,
        ticket_id=scope.ticket_id,
        question=masked.sanitized_text,
        sql=validation.sql,
        outcome="success",
        row_count=answer.row_count,
        duration_ms=_elapsed(started),
        category=None,
    )
    logger.info(
        "sql_query user_id=%s role=%s mode=%s outcome=success rows=%s duration_ms=%s",
        principal.user_id,
        principal.role,
        scope.mode,
        answer.row_count,
        _elapsed(started),
    )
    return answer


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _reject(settings: Settings, principal, scope: AccessScope, question: str, sql: str, category: str, started: float) -> SqlAnswer:
    del settings
    _audit(
        user_id=principal.user_id,
        role=principal.role,
        mode=scope.mode,
        ticket_id=scope.ticket_id,
        question=question,
        sql=sql,
        outcome="rejected",
        row_count=0,
        duration_ms=_elapsed(started),
        category=category,
    )
    logger.info(
        "sql_query user_id=%s role=%s mode=%s outcome=rejected category=%s",
        principal.user_id,
        principal.role,
        scope.mode,
        category,
    )
    return _answer(ok=False, category=category, scope=scope)


def list_ticket_overview() -> dict[str, Any]:
    principal = current_principal()
    if principal.role != "instructor":
        raise AuthorizationError("Only instructors can view assigned tickets.")
    port = get_ticket_access()
    cards = [_public_card(grant) for grant in port.grants_for_instructor(principal.user_id)]
    return {"r3_connected": port.r3_available(), "tickets": cards}


def ticket_context(ticket_id: str) -> dict[str, Any]:
    """Sanitized handoff context for one ticket assigned to the caller."""
    principal = current_principal()
    started = time.perf_counter()
    try:
        scope = resolve_scope(ticket_id)
    except SqlTicketNotFoundError:
        _audit(
            user_id=principal.user_id,
            role=principal.role,
            mode="instructor_ticket",
            ticket_id=(ticket_id or "")[:64] or None,
            question="ticket context",
            sql="",
            outcome="rejected",
            row_count=0,
            duration_ms=_elapsed(started),
            category="unassigned_ticket",
        )
        raise
    if scope.mode != "instructor_ticket":
        raise SqlTicketNotFoundError()
    grant = next(
        item
        for item in get_ticket_access().grants_for_instructor(scope.principal_id)
        if item.ticket_id == scope.ticket_id
    )
    repairs = []
    for run in reversed(load_scoped_runs(scope)):
        repairs.append(
            {
                "run_id": run.id,
                "created_at": run.created_at.isoformat() if run.created_at else "",
                "status": run.status,
                "generated_code": mask_sensitive_data(run.generated_code or "").sanitized_text,
                "prompt": mask_sensitive_data(run.sanitised_request or "").sanitized_text,
            }
        )
    return {"ticket": _public_card(grant), "repairs": repairs}


def _public_card(grant) -> dict[str, Any]:
    return {
        "ticket_id": grant.ticket_id,
        "priority": grant.priority,
        "created_at": grant.created_at,
        "sla_status": grant.sla_status,
        "student_ref": grant.student_ref,
        "sanitised_request": mask_sensitive_data(grant.sanitised_request).sanitized_text,
        "handoff_summary": mask_sensitive_data(grant.handoff_summary).sanitized_text,
        "attempts": grant.attempts,
        "last_failing_test": mask_sensitive_data(grant.last_failing_test).sanitized_text,
        "run_id": grant.run_ids[0] if grant.run_ids else None,
    }
