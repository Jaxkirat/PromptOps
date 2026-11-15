"""Human approval records and atomic decisions.

Identity comes from the request context. Clients cannot supply an approver id.
Students cannot approve their own runs. A second decision loses the race.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import update

from codeforge.auth.identity import current_principal
from codeforge.config.settings import get_settings
from codeforge.database.database import init_db, session_scope
from codeforge.database.models import ROLE_INSTRUCTOR, ApprovalRequest, Run, User
from codeforge.exceptions import ApprovalConflictError, ApprovalNotFoundError, AuthorizationError

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    """Naive UTC so SQLite round-trips compare cleanly."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_approval(
    *,
    user_id: str,
    run_id: str,
    thread_id: str,
    reasons: list[str],
    operations: list[str],
    code_text: str,
    tests_text: str,
    summary: str,
) -> str:
    init_db()
    expires = _utcnow() + timedelta(minutes=get_settings().approval_expiry_minutes)
    with session_scope() as db:
        row = ApprovalRequest(
            user_id=user_id,
            run_id=run_id,
            thread_id=thread_id,
            status="pending",
            reasons_json=json.dumps(reasons),
            operations_json=json.dumps(operations),
            code_text=code_text,
            tests_text=tests_text,
            summary=summary[:500],
            expires_at=expires,
        )
        db.add(row)
        db.flush()
        approval_id = row.id
    logger.info("approval_created id=%s user_id=%s run_id=%s", approval_id, user_id, run_id)
    return approval_id


def list_pending() -> list[dict[str, Any]]:
    """Instructor queue. Students are rejected before any rows are read."""
    principal = current_principal()
    if principal.role != ROLE_INSTRUCTOR:
        raise AuthorizationError("Pending approvals are visible to instructors only.")
    init_db()
    now = _utcnow()
    with session_scope() as db:
        rows = (
            db.query(ApprovalRequest, User.full_name)
            .join(User, User.id == ApprovalRequest.user_id)
            .filter(ApprovalRequest.status == "pending", ApprovalRequest.expires_at > now)
            .order_by(ApprovalRequest.created_at.asc())
            .all()
        )
        return [_public(row, name) for row, name in rows]


def get_approval(approval_id: str) -> dict[str, Any]:
    principal = current_principal()
    init_db()
    with session_scope() as db:
        found = (
            db.query(ApprovalRequest, User.full_name)
            .join(User, User.id == ApprovalRequest.user_id)
            .filter(ApprovalRequest.id == approval_id)
            .one_or_none()
        )
        if found is None:
            raise ApprovalNotFoundError()
        row, name = found
        if principal.role != ROLE_INSTRUCTOR and principal.user_id != row.user_id:
            raise ApprovalNotFoundError()
        return _public(row, name, include_code=True)


def decide(approval_id: str, decision: str) -> dict[str, Any]:
    """Atomically approve or reject, then resume the checkpointed graph."""
    if decision not in {"approved", "rejected"}:
        raise ValueError("Decision must be approved or rejected.")
    principal = current_principal()
    init_db()
    with session_scope() as db:
        row = db.get(ApprovalRequest, approval_id)
        if row is None:
            raise ApprovalNotFoundError()
        if principal.role != ROLE_INSTRUCTOR and principal.user_id != row.user_id:
            raise ApprovalNotFoundError()
        if principal.role != ROLE_INSTRUCTOR or principal.user_id == row.user_id:
            raise AuthorizationError("Students cannot approve their own requests.")
        now = _utcnow()
        result = db.execute(
            update(ApprovalRequest)
            .where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.status == "pending",
                ApprovalRequest.expires_at > now,
            )
            .values(status=decision, approver_id=principal.user_id, decided_at=now)
        )
        if result.rowcount != 1:
            current = db.get(ApprovalRequest, approval_id)
            if current is not None and current.expires_at <= now:
                raise ApprovalConflictError("Approval request has expired.")
            raise ApprovalConflictError()
        thread_id = row.thread_id
        run_id = row.run_id
        db.commit()

    logger.info(
        "approval_decided id=%s decision=%s approver_id=%s",
        approval_id,
        decision,
        principal.user_id,
    )
    try:
        state = resume_graph(thread_id, {"decision": decision, "actor_id": principal.user_id})
    except Exception as exc:  # noqa: BLE001 - decision is already durable
        message = f"Graph resume failed after the decision was saved: {exc}"
        logger.exception("approval_resume_failed id=%s", approval_id)
        with session_scope() as db:
            current = db.get(ApprovalRequest, approval_id)
            if current is not None:
                current.resume_error = message[:2000]
        raise ApprovalConflictError(message) from exc

    if run_id:
        _update_run_from_state(run_id, state)
    return get_approval(approval_id)


def resume_graph(thread_id: str, resume: dict[str, Any]) -> dict[str, Any]:
    """Indirection so tests can replace graph resume without a live model."""
    from codeforge.graph.workflow import run_codeforge

    return run_codeforge("", thread_id=thread_id, resume=resume)


def _update_run_from_state(run_id: str, state: dict[str, Any]) -> None:
    report = state.get("report")
    if report is None:
        return
    from codeforge.services.run_service import artifacts_from_report

    execution = getattr(report, "execution", None)
    with session_scope() as db:
        run = db.get(Run, run_id)
        if run is None:
            return
        run.status = report.status
        artifacts = artifacts_from_report(report)
        artifacts["approval_status"] = getattr(execution, "approval_status", None) if execution else None
        run.artifacts_json = json.dumps(artifacts)
        if execution is not None:
            run.execution_time = execution.execution_time_seconds
            run.test_results = json.dumps(
                {
                    "total": execution.total_tests,
                    "passed": execution.passed_tests,
                    "failed": execution.failed_tests,
                    "skipped": execution.skipped_tests,
                    "exit_code": execution.exit_code,
                    "timed_out": execution.timed_out,
                }
            )


def _public(row: ApprovalRequest, owner_name: str, include_code: bool = False) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "run_id": row.run_id,
        "status": row.status,
        "summary": row.summary,
        "owner_name": owner_name,
        "reasons": json.loads(row.reasons_json or "[]"),
        "operations": json.loads(row.operations_json or "[]"),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "resume_error": row.resume_error,
    }
    if include_code:
        payload["code_preview"] = row.code_text[:4000]
        payload["tests_preview"] = row.tests_text[:4000]
    return payload
