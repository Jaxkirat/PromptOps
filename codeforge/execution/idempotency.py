"""Persistent execution idempotency.

Key = SHA256(canonical JSON of user_id, code, tests). Stored in SQLite/Postgres
via SQLAlchemy with a unique constraint. Empty user ids are not deduplicated
(CLI runs without an authenticated principal).
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from sqlalchemy.exc import IntegrityError

from codeforge.database.database import init_db, session_scope
from codeforge.database.models import ExecutionRecord
from codeforge.models.schemas import ExecutionResult

logger = logging.getLogger(__name__)

TERMINAL_STATES = {
    "completed",
    "denied",
    "rejected",
    "failed",
    "timeout",
    "unavailable",
    "passed",
}


def idempotency_key(user_id: str, code: str, tests: str) -> str:
    payload = json.dumps(
        {"user_id": user_id, "code": code, "tests": tests},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def lookup_execution(user_id: str, key: str) -> ExecutionRecord | None:
    if not user_id:
        return None
    init_db()
    with session_scope() as db:
        row = (
            db.query(ExecutionRecord)
            .filter(ExecutionRecord.idempotency_key == key, ExecutionRecord.user_id == user_id)
            .one_or_none()
        )
        if row is not None:
            db.expunge(row)
        return row


def claim_execution(
    *,
    user_id: str,
    key: str,
    state: str,
    policy_decision: str,
    reasons: list[str],
) -> tuple[ExecutionRecord | None, bool]:
    """Insert a new record. Returns (existing_or_new, created).

    On conflict, returns the existing row and created=False so a second
    request does not execute again.
    """
    if not user_id:
        return None, True
    init_db()
    try:
        with session_scope() as db:
            row = ExecutionRecord(
                idempotency_key=key,
                user_id=user_id,
                state=state,
                policy_decision=policy_decision,
                policy_reasons_json=json.dumps(reasons),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            db.expunge(row)
            return row, True
    except IntegrityError:
        existing = lookup_execution(user_id, key)
        logger.info("idempotency_hit user_id=%s key=%s", user_id, key[:12])
        return existing, False


def store_result(user_id: str, key: str, state: str, result: ExecutionResult) -> None:
    if not user_id:
        return
    init_db()
    with session_scope() as db:
        row = (
            db.query(ExecutionRecord)
            .filter(ExecutionRecord.idempotency_key == key, ExecutionRecord.user_id == user_id)
            .one_or_none()
        )
        if row is None:
            return
        row.state = state
        row.result_json = result.model_dump_json()
        row.sandbox_backend = result.sandbox_backend
        db.add(row)


def result_from_record(row: ExecutionRecord) -> ExecutionResult | None:
    if not row.result_json:
        return None
    data: dict[str, Any] = json.loads(row.result_json)
    result = ExecutionResult.model_validate(data)
    result.idempotency_status = "hit"
    result.executed = False
    return result
