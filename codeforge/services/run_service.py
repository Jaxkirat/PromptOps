"""Run service: privacy-first ingestion pipeline, persistence and isolation.

Ingestion order (R1 requirement):

    authenticated identity (request context) -> input validation ->
    PII/secret masking -> atomic quota reservation -> CodeForge pipeline ->
    sanitised persistence -> response

The raw request never reaches the LLM, the database or the logs.

Isolation: :func:`get_my_runs` and :func:`get_run` take NO user id argument.
The owner is resolved internally from the trusted request context and every
query filters by owner. A missing run and a foreign-owned run raise the same
:class:`RunNotFoundError`.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Callable, Optional

from pydantic import BaseModel

from codeforge.auth.identity import current_principal
from codeforge.database.database import session_scope
from codeforge.database.models import Run
from codeforge.database.repositories import run_repository
from codeforge.exceptions import RunNotFoundError
from codeforge.privacy.masker import mask_sensitive_data
from codeforge.privacy.sanitization import sanitize_for_storage
from codeforge.services import quota_service

logger = logging.getLogger(__name__)

MAX_REQUEST_LENGTH = 8000

# Injectable pipeline runner: sanitized request -> final LangGraph state.
# Tests and demos inject fakes; production lazily builds the real workflow.
PipelineRunner = Callable[[str], dict[str, Any]]
_pipeline_runner: PipelineRunner | None = None


def set_pipeline_runner(runner: PipelineRunner | None) -> None:
    """Inject (or reset to default) the pipeline runner."""
    global _pipeline_runner
    _pipeline_runner = runner


def _get_pipeline_runner() -> PipelineRunner:
    global _pipeline_runner
    if _pipeline_runner is None:
        from codeforge.graph.workflow import build_workflow

        app = build_workflow()
        _pipeline_runner = lambda text: app.invoke({"user_request": text})  # noqa: E731
    return _pipeline_runner


class RunRecord(BaseModel):
    """Safe, serialisable view of a persisted run."""

    id: str
    sanitised_request: str
    task_type: Optional[str]
    language: Optional[str]
    status: str
    generated_code: Optional[str]
    generated_tests: Optional[str]
    test_results: Optional[dict[str, Any]]
    execution_time: Optional[float]
    redaction_count: int
    created_at: datetime


def _to_record(run: Run) -> RunRecord:
    return RunRecord(
        id=run.id,
        sanitised_request=run.sanitised_request,
        task_type=run.task_type,
        language=run.language,
        status=run.status,
        generated_code=run.generated_code,
        generated_tests=run.generated_tests,
        test_results=json.loads(run.test_results) if run.test_results else None,
        execution_time=run.execution_time,
        redaction_count=run.redaction_count,
        created_at=run.created_at,
    )


def submit_code_request(request_text: str) -> RunRecord:
    """Run the full privacy-first pipeline for the authenticated user."""
    principal = current_principal()

    # 1. Input validation.
    if not request_text or not request_text.strip():
        raise ValueError("Request must not be empty.")
    if len(request_text) > MAX_REQUEST_LENGTH:
        raise ValueError(f"Request exceeds the maximum length of {MAX_REQUEST_LENGTH} characters.")

    # 2. PII and secret masking — BEFORE quota, LLM, persistence or logging.
    masking = mask_sensitive_data(request_text.strip())
    sanitized = masking.sanitized_text

    # 3. Atomic quota reservation — the pipeline is never invoked if this fails.
    quota_service.reserve_run(principal.user_id)

    # 4. CodeForge pipeline (LangGraph) with the SANITIZED request only.
    started = time.monotonic()
    state = _get_pipeline_runner()(sanitized)
    duration = round(time.monotonic() - started, 3)

    report = state.get("report")

    # 5. Sanitised persistence (defence in depth on generated content).
    test_results_json: str | None = None
    task_type = language = None
    status = "generation_error"
    generated_code = generated_tests = None
    execution_time = duration

    if report is not None:
        status = report.status
        task_type = report.task_type
        language = report.language
        generated_code = sanitize_for_storage(report.code.code if report.code else None)
        generated_tests = sanitize_for_storage(report.tests.test_code if report.tests else None)
        if report.execution is not None:
            execution_time = report.execution.execution_time_seconds
            test_results_json = json.dumps(
                {
                    "total": report.execution.total_tests,
                    "passed": report.execution.passed_tests,
                    "failed": report.execution.failed_tests,
                    "skipped": report.execution.skipped_tests,
                    "exit_code": report.execution.exit_code,
                    "timed_out": report.execution.timed_out,
                }
            )

    with session_scope() as db:
        run = run_repository.create(
            db,
            Run(
                user_id=principal.user_id,
                sanitised_request=sanitized,
                task_type=task_type,
                language=language,
                status=status,
                generated_code=generated_code,
                generated_tests=generated_tests,
                test_results=test_results_json,
                execution_time=execution_time,
                redaction_count=masking.redaction_count,
            ),
        )
        db.commit()
        record = _to_record(run)

    # 6. Structured logging — metadata only, never content.
    logger.info(
        "run_completed run_id=%s user_id=%s status=%s redactions=%d categories=%s duration=%.3f",
        record.id,
        principal.user_id,
        status,
        masking.redaction_count,
        ",".join(masking.redaction_categories) or "none",
        duration,
    )
    return record


def get_my_runs() -> list[RunRecord]:
    """All runs of the authenticated user. Takes NO user id argument."""
    principal = current_principal()
    with session_scope() as db:
        return [_to_record(run) for run in run_repository.list_for_owner(db, principal.user_id)]


def get_run(run_id: str) -> RunRecord:
    """One run of the authenticated user. Takes NO user id argument.

    Raises:
        RunNotFoundError: identically for missing and foreign-owned runs.
    """
    principal = current_principal()
    with session_scope() as db:
        run = run_repository.get_for_owner(db, principal.user_id, run_id)
        if run is None:
            raise RunNotFoundError()
        return _to_record(run)
