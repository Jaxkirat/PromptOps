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
from datetime import datetime, timezone
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

        def _default(text: str) -> dict[str, Any]:
            from codeforge.graph.workflow import run_codeforge

            principal = current_principal()
            return run_codeforge(text, user_id=principal.user_id)

        _pipeline_runner = _default
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
    artifacts: Optional[dict[str, Any]] = None


def artifacts_from_report(report: Any) -> dict[str, Any]:
    """Extract UI-facing artifacts. Never includes the raw unsanitized request."""
    artifacts: dict[str, Any] = {
        "status_detail": getattr(report, "status_detail", "") or "",
        "generation_successful": bool(getattr(report, "generation_successful", False)),
        "execution_successful": bool(getattr(report, "execution_successful", False)),
        "tests_passed": bool(getattr(report, "tests_passed", False)),
        "explanation": "",
        "router": None,
        "requirements": None,
        "stdout": "",
        "stderr": "",
        "error_message": None,
        "timed_out": False,
        "exit_code": None,
    }
    if report is None:
        return artifacts

    code = getattr(report, "code", None)
    if code is not None:
        artifacts["explanation"] = sanitize_for_storage(code.explanation) or ""

    router = getattr(report, "router_output", None)
    if router is not None:
        artifacts["router"] = {
            "task_type": router.task_type,
            "language": router.language,
            "description": router.description,
            "confidence": router.confidence,
            "reasoning": router.reasoning,
        }

    requirements = getattr(report, "requirements", None)
    if requirements is not None:
        artifacts["requirements"] = json.loads(requirements.model_dump_json())

    execution = getattr(report, "execution", None)
    if execution is not None:
        artifacts["stdout"] = sanitize_for_storage(execution.stdout) or ""
        artifacts["stderr"] = sanitize_for_storage(execution.stderr) or ""
        artifacts["error_message"] = sanitize_for_storage(execution.error_message)
        artifacts["timed_out"] = bool(execution.timed_out)
        artifacts["exit_code"] = execution.exit_code
        artifacts["policy_decision"] = execution.policy_decision
        artifacts["policy_reasons"] = list(execution.policy_reasons or [])
        artifacts["approval_status"] = execution.approval_status
        artifacts["sandbox_backend"] = execution.sandbox_backend
        artifacts["network_isolated"] = execution.network_isolated
        artifacts["filesystem_isolated"] = execution.filesystem_isolated
        artifacts["idempotency_status"] = execution.idempotency_status
        artifacts["executed"] = bool(execution.executed)
    return artifacts


def _to_record(run: Run) -> RunRecord:
    artifacts = json.loads(run.artifacts_json) if run.artifacts_json else None
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
        artifacts=artifacts,
    )


def submit_code_request(request_text: str, conversation_id: str | None = None) -> RunRecord:
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

    from codeforge.escalation.rules import next_negative_count, should_escalate
    from codeforge.escalation.service import load_escalation_state
    from codeforge.escalation.triage import triage_text

    triage = triage_text(sanitized)
    prior = (
        load_escalation_state(conversation_id)
        if conversation_id
        else {"consecutive_negative": 0, "repair_failures": 0, "policy_denials": 0}
    )
    preview = should_escalate(
        triage,
        next_negative_count(prior["consecutive_negative"], triage.sentiment),
        prior["repair_failures"],
        prior["policy_denials"],
    )
    skip_pipeline = preview.should_escalate and preview.trigger_reason in {
        "explicit_human",
        "angry_sentiment",
        "two_negative",
    }

    # 4. Verified template or the CodeForge pipeline. Templates still use R2.
    started = time.monotonic()
    from codeforge.resilience.errors import AllProvidersFailed
    from codeforge.templates.library import match_template
    from codeforge.templates.runner import run_template

    template = None if skip_pipeline else match_template(sanitized)
    provider_down = False
    if skip_pipeline:
        state = {"report": None}
    elif template is not None:
        state = run_template(sanitized, template)
    else:
        try:
            state = _get_pipeline_runner()(sanitized)
        except AllProvidersFailed:
            state = {"report": None, "provider_down": True}
            provider_down = True
    duration = round(time.monotonic() - started, 3)

    report = state.get("report")
    interrupt = state.get("approval_interrupt")

    # 5. Sanitised persistence (defence in depth on generated content).
    test_results_json: str | None = None
    task_type = language = None
    status = "generation_error"
    generated_code = generated_tests = None
    execution_time = duration

    artifacts: dict[str, Any] | None = None
    if interrupt and report is None:
        status = "awaiting_approval"
        code_output = state.get("code_output")
        test_output = state.get("test_output")
        router_output = state.get("router_output")
        generated_code = sanitize_for_storage(getattr(code_output, "code", None))
        generated_tests = sanitize_for_storage(getattr(test_output, "test_code", None))
        task_type = getattr(router_output, "task_type", None)
        language = getattr(router_output, "language", None)
        policy = state.get("policy_result") or {}
        artifacts = {
            "status_detail": "Execution paused: human approval required.",
            "generation_successful": True,
            "execution_successful": False,
            "tests_passed": False,
            "executed": False,
            "policy_decision": policy.get("decision"),
            "policy_reasons": policy.get("reasons") or [],
            "approval_status": "pending",
            "operations": policy.get("detected_operations") or [],
            "thread_id": state.get("thread_id"),
            "stdout": "",
            "stderr": "",
            "exit_code": None,
            "timed_out": False,
            "error_message": "Execution paused: human approval required.",
        }
    elif provider_down:
        status = "generation_error"
        artifacts = {
            "status_detail": (
                "Code generation is temporarily unavailable. "
                "You can ask to talk to an instructor if you want a person to help."
            ),
            "generation_successful": False,
            "execution_successful": False,
            "tests_passed": False,
            "executed": False,
            "generation_source": "unavailable",
        }
    elif skip_pipeline:
        status = "escalated"
        artifacts = {
            "status_detail": "This request was escalated to an instructor.",
            "generation_successful": False,
            "execution_successful": False,
            "tests_passed": False,
            "executed": False,
        }
    elif report is not None:
        status = report.status
        task_type = report.task_type
        language = report.language
        generated_code = sanitize_for_storage(report.code.code if report.code else None)
        generated_tests = sanitize_for_storage(report.tests.test_code if report.tests else None)
        artifacts = artifacts_from_report(report)
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

    if isinstance(artifacts, dict):
        artifacts.update(state.get("resilience") or {})

    with session_scope() as db:
        from codeforge.database.models import Conversation, Message

        conversation = None
        if conversation_id:
            conversation = db.get(Conversation, conversation_id)
            if conversation is None or conversation.user_id != principal.user_id:
                conversation = None
        if conversation is None:
            conversation = Conversation(
                user_id=principal.user_id,
                title=(sanitized[:80] or "CodeForge request"),
            )
            db.add(conversation)
            db.flush()
        run = run_repository.create(
            db,
            Run(
                user_id=principal.user_id,
                conversation_id=conversation.id,
                sanitised_request=sanitized,
                task_type=task_type,
                language=language,
                status=status,
                generated_code=generated_code,
                generated_tests=generated_tests,
                test_results=test_results_json,
                artifacts_json=json.dumps(artifacts) if artifacts is not None else None,
                execution_time=execution_time,
                redaction_count=masking.redaction_count,
                completed_at=None if status == "awaiting_approval" else datetime.now(timezone.utc),
            ),
        )
        db.add(
            Message(
                conversation_id=conversation.id,
                run_id=run.id,
                role="user",
                content=sanitized,
            )
        )
        db.add(
            Message(
                conversation_id=conversation.id,
                run_id=run.id,
                role="assistant",
                content=status,
            )
        )
        db.commit()
        stored_conversation_id = conversation.id
        stored_run_id = run.id
        record = _to_record(run)
        if interrupt and report is None:
            from codeforge.services.approval_service import create_approval

            policy = state.get("policy_result") or {}
            create_approval(
                user_id=principal.user_id,
                run_id=record.id,
                thread_id=str(state.get("thread_id") or ""),
                reasons=list(policy.get("reasons") or []),
                operations=list(policy.get("detected_operations") or []),
                code_text=generated_code or "",
                tests_text=generated_tests or "",
                summary=sanitized,
            )

    record.artifacts = _record_escalation(
        sanitized, stored_conversation_id, stored_run_id, status, record.artifacts
    )
    with session_scope() as db:
        stored = db.get(Run, record.id)
        if stored is not None:
            stored.artifacts_json = json.dumps(record.artifacts)

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


def _record_escalation(sanitized: str, conversation_id: str, run_id: str, status: str, artifacts: dict | None) -> dict:
    from codeforge.escalation.rules import next_negative_count, should_escalate
    from codeforge.escalation.service import (
        load_escalation_state,
        open_ticket,
        save_escalation_state,
        student_message,
    )
    from codeforge.escalation.triage import triage_text

    triage = triage_text(sanitized)
    state = load_escalation_state(conversation_id)
    negative = next_negative_count(state["consecutive_negative"], triage.sentiment)
    repairs = state["repair_failures"] + (
        1 if status in {"tests_failed", "execution_error", "execution_timeout"} else 0
    )
    denials = state["policy_denials"] + (1 if status == "denied" else 0)
    decision = should_escalate(triage, negative, repairs, denials)
    save_escalation_state(
        conversation_id,
        {"consecutive_negative": negative, "repair_failures": repairs, "policy_denials": denials},
    )
    updated = dict(artifacts or {})
    updated["conversation_id"] = conversation_id
    if decision.should_escalate:
        ticket = open_ticket(conversation_id, run_id, decision)
        updated["ticket"] = ticket
        updated["status_detail"] = student_message(ticket)
    return updated


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
