"""Thumbs feedback. Identity comes from the principal, never from the client."""

from __future__ import annotations

import logging
from datetime import datetime

from pydantic import BaseModel

from codeforge.auth.identity import current_principal
from codeforge.database.database import session_scope
from codeforge.database.models import RunFeedback
from codeforge.exceptions import FeedbackConflictError, RunNotFoundError
from codeforge.privacy.masker import mask_sensitive_data
from codeforge.services.run_service import get_run

logger = logging.getLogger(__name__)


class FeedbackRecord(BaseModel):
    id: str
    run_id: str
    vote: str
    explanation: str
    sanitised_request: str
    result_ref: str
    status: str
    created_at: datetime


def submit_feedback(run_id: str, vote: str, explanation: str = "") -> FeedbackRecord:
    if vote not in {"up", "down"}:
        raise ValueError("vote must be up or down")
    principal = current_principal()
    run = get_run(run_id)
    masked = mask_sensitive_data(explanation or "")
    result_ref = f"status={run.status}; task_type={run.task_type or 'unknown'}"
    with session_scope() as db:
        existing = (
            db.query(RunFeedback)
            .filter(RunFeedback.user_id == principal.user_id, RunFeedback.run_id == run.id)
            .one_or_none()
        )
        if existing is not None:
            raise FeedbackConflictError()
        row = RunFeedback(
            user_id=principal.user_id,
            run_id=run.id,
            vote=vote,
            explanation=masked.sanitized_text,
            sanitised_request=run.sanitised_request,
            result_ref=result_ref,
            status="recorded",
        )
        db.add(row)
        db.flush()
        record = _to_record(row)
    logger.info(
        "feedback_recorded id=%s run_id=%s user_id=%s vote=%s redactions=%d",
        record.id,
        run.id,
        principal.user_id,
        vote,
        masked.redaction_count,
    )
    return record


def get_feedback(feedback_id: str) -> FeedbackRecord:
    """Owner-only read. Missing and foreign feedback are the same not-found error."""
    principal = current_principal()
    with session_scope() as db:
        row = db.get(RunFeedback, feedback_id)
        if row is None or row.user_id != principal.user_id:
            raise RunNotFoundError()
        return _to_record(row)


def get_feedback_for_run(run_id: str) -> FeedbackRecord:
    principal = current_principal()
    get_run(run_id)
    with session_scope() as db:
        row = (
            db.query(RunFeedback)
            .filter(RunFeedback.user_id == principal.user_id, RunFeedback.run_id == run_id)
            .one_or_none()
        )
        if row is None:
            raise RunNotFoundError()
        return _to_record(row)


def _to_record(row: RunFeedback) -> FeedbackRecord:
    return FeedbackRecord(
        id=row.id,
        run_id=row.run_id,
        vote=row.vote,
        explanation=row.explanation,
        sanitised_request=row.sanitised_request,
        result_ref=row.result_ref,
        status=row.status,
        created_at=row.created_at,
    )
