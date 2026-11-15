"""Pure presentation helpers for the Gradio workspace.

These functions never call agents, never mask data, and never compute quotas.
They only format values already returned by the backend.
"""

from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

from codeforge.services.quota_service import QuotaStatus
from codeforge.services.run_service import RunRecord
from codeforge.services.user_service import UserProfile

_STATUS_LABELS = {
    "success": "Tests passed",
    "tests_failed": "Tests failed",
    "execution_timeout": "Execution timed out",
    "execution_error": "Execution error",
    "generation_error": "Generation error",
    "unsupported": "Unsupported",
    "denied": "Blocked by policy",
    "awaiting_approval": "Awaiting approval",
    "rejected": "Rejected",
    "unavailable": "Sandbox unavailable",
    "escalated": "Passed to an instructor",
}


def status_label(status: str) -> str:
    return _STATUS_LABELS.get(status, status.replace("_", " ").title())


def status_tone(status: str) -> str:
    if status == "success":
        return "ok"
    if status in {"tests_failed", "execution_error", "generation_error", "denied", "rejected"}:
        return "err"
    if status in {"execution_timeout", "unsupported", "awaiting_approval", "unavailable"}:
        return "warn"
    return "muted"


def assistant_message(run: RunRecord) -> str:
    """Markdown shown in the chat transcript for a completed run."""
    artifacts = run.artifacts or {}
    router = artifacts.get("router") or {}
    task_type = run.task_type or router.get("task_type") or "unknown"
    language = run.language or router.get("language") or "unknown"
    confidence = router.get("confidence")
    detail = artifacts.get("status_detail") or ""
    tests = run.test_results or {}

    lines = [
        f"**{status_label(run.status)}**",
        "",
        f"Task type: `{task_type}` · Language: `{language}`",
    ]
    if isinstance(confidence, (int, float)):
        lines.append(f"Router confidence: `{confidence:.2f}`")
    if detail:
        lines.append("")
        lines.append(detail)
    ticket = artifacts.get("ticket") or {}
    if ticket.get("id"):
        lines.append("")
        lines.append(
            f"Support ticket `{ticket['id']}` is {ticket.get('priority', 'P1')}. "
            "An instructor is expected to respond within 4 hours."
        )
    usage = artifacts.get("llm_usage") or {}
    if usage.get("agents"):
        lines.append("")
        lines.append("Run usage")
        for name, bucket in usage["agents"].items():
            tokens = int(bucket.get("input_tokens") or 0) + int(bucket.get("output_tokens") or 0)
            lines.append(f"- {name}: {tokens} tokens")

    if run.status == "unsupported":
        if task_type == "sql":
            lines.append(
                "\nSQL generation is **not implemented** in this phase "
                "(planned: R7 Safe SQL Agent). No code was generated."
            )
        else:
            lines.append("\nNo Python function was generated for this request.")
    else:
        passed = tests.get("passed")
        failed = tests.get("failed")
        total = tests.get("total")
        if total:
            lines.append("")
            lines.append(f"Pytest: **{passed} passed**, {failed} failed, {total} total.")
            if run.status != "success":
                lines.append("This is not a success — inspect the Tests and Execution tabs.")
        lines.append("\nOpen the **Code**, **Tests**, **Requirements** and **Execution** tabs for artifacts.")

    lines.append(
        "\n_Execution uses a development-grade subprocess runner. "
        "The R2 security sandbox is not implemented yet._"
    )
    return "\n".join(lines)


def requirements_markdown(run: RunRecord | None) -> str:
    if run is None:
        return "_No run selected. Submit a request or open a previous run._"
    req = (run.artifacts or {}).get("requirements")
    if not req:
        if run.status == "unsupported":
            return "_Requirements were not extracted — this request was not a supported Python task._"
        return "_Requirements were not stored for this run._"

    def _list(title: str, items: list[str]) -> str:
        if not items:
            return ""
        bullets = "\n".join(f"- {item}" for item in items)
        return f"### {title}\n{bullets}\n"

    params = req.get("parameters") or []
    param_lines = []
    for param in params:
        required = "required" if param.get("required", True) else "optional"
        param_lines.append(
            f"- `{param.get('name')}`: `{param.get('data_type')}` ({required})"
            + (f" — {param.get('description')}" if param.get("description") else "")
        )

    parts = [
        f"## `{req.get('function_name') or 'Not specified'}`",
        "",
        req.get("description") or "Not specified",
        "",
        f"- **Language:** {req.get('language') or 'Not specified'}",
        f"- **Returns:** `{req.get('return_type') or 'Not specified'}`",
        "",
        "### Parameters",
        "\n".join(param_lines) if param_lines else "_Not specified_",
        "",
        _list("Expected behaviour", req.get("expected_behavior") or []),
        _list("Edge cases", req.get("edge_cases") or []),
        _list("Constraints", req.get("constraints") or []),
        _list("Implementation notes", req.get("implementation_notes") or []),
    ]
    return "\n".join(part for part in parts if part is not None)


def execution_markdown(run: RunRecord | None) -> str:
    if run is None:
        return "_No execution result yet._"
    artifacts = run.artifacts or {}
    tests = run.test_results or {}
    generated = bool(run.generated_code)
    tests_generated = bool(run.generated_tests)
    executed = bool(artifacts.get("executed")) or (
        tests.get("exit_code") is not None and run.status in {"success", "tests_failed", "execution_timeout"}
    )
    passed = executed and (bool(artifacts.get("tests_passed")) or run.status == "success")
    decision = artifacts.get("policy_decision") or "not evaluated"
    reasons = artifacts.get("policy_reasons") or []
    reason_text = "\n".join(f"- {reason}" for reason in reasons) or "_None recorded._"

    lines = [
        "## Policy status",
        "",
        f"**{decision}**",
        "",
        reason_text,
        "",
        "## Execution status",
        "",
        f"**{status_label(run.status)}**",
        "",
        f"- Code generated: **{'yes' if generated else 'no'}**",
        f"- Tests generated: **{'yes' if tests_generated else 'no'}**",
        f"- Tests executed: **{'yes' if executed else 'no'}**",
        f"- Tests passed: **{'yes' if passed else 'no'}**",
        "",
        f"- Sandbox: `{artifacts.get('sandbox_backend') or 'not started'}`",
        f"- Network isolated: `{artifacts.get('network_isolated')}`",
        f"- Filesystem isolated: `{artifacts.get('filesystem_isolated')}`",
        f"- Idempotency: `{artifacts.get('idempotency_status') or 'n/a'}`",
        f"- Approval: `{artifacts.get('approval_status') or 'n/a'}`",
        "",
        f"- Pytest passed: `{tests.get('passed', 0) if executed else 0}`",
        f"- Pytest failed: `{tests.get('failed', 0) if executed else 0}`",
        f"- Pytest skipped: `{tests.get('skipped', 0) if executed else 0}`",
        f"- Total collected: `{tests.get('total', 0) if executed else 0}`",
        f"- Exit code: `{artifacts.get('exit_code', tests.get('exit_code')) if executed else None}`",
        f"- Duration: `{run.execution_time if run.execution_time is not None else '—'}s`",
        f"- Timed out: `{artifacts.get('timed_out', tests.get('timed_out'))}`",
    ]
    if run.status == "awaiting_approval":
        lines += ["", "**Execution paused: human approval required.**"]
    if artifacts.get("error_message"):
        lines += ["", f"**Note:** {artifacts['error_message']}"]
    lines += ["", "<details><summary>Captured logs</summary>", "", "See the stdout and stderr boxes below.", "", "</details>"]
    return "\n".join(lines)


def tests_summary_markdown(run: RunRecord | None) -> str:
    if run is None:
        return "_No tests yet._"
    tests = run.test_results or {}
    artifacts = run.artifacts or {}
    if not run.generated_tests:
        return "_No tests were generated for this run._"
    if tests.get("exit_code") is None and artifacts.get("exit_code") is None:
        return "Tests were generated but **not executed**."
    passed = tests.get("passed", 0)
    failed = tests.get("failed", 0)
    total = tests.get("total", 0)
    duration = run.execution_time
    tone = "passed" if run.status == "success" else "failed"
    if run.status == "success":
        headline = f"**{passed} tests passed**, {failed} failed"
    elif run.status == "tests_failed":
        headline = f"**{failed} tests failed**, {passed} passed — not a success"
    else:
        headline = f"**Execution did not succeed** ({status_label(run.status)})"
    extra = f" · {total} total"
    if duration is not None:
        extra += f" · {duration:.2f}s"
    extra += f" · pytest exit `{tests.get('exit_code', artifacts.get('exit_code'))}`"
    return f"{headline}{extra}\n\n_Result source: stored pytest outcome, tone=`{tone}`._"


def quota_html(quota: QuotaStatus | None) -> str:
    if quota is None:
        return '<div class="muted">Sign in to see usage.</div>'
    used_pct = 0 if quota.limit <= 0 else min(100, round(100 * quota.used / quota.limit))
    reset = quota.resets_at.replace("T", " ").replace("+00:00", " UTC")
    return (
        '<div class="quota">'
        f'<div class="quota-meta">{quota.used} / {quota.limit} runs today'
        f'<span>{quota.remaining} remaining</span></div>'
        f'<div class="quota-track"><div class="quota-fill" style="width:{used_pct}%"></div></div>'
        f'<div class="quota-reset">Resets {escape(reset)}</div>'
        "</div>"
    )


def history_choices(runs: list[RunRecord]) -> list[tuple[str, str]]:
    choices: list[tuple[str, str]] = []
    for run in runs:
        summary = " ".join(run.sanitised_request.split())[:42] or "(empty)"
        created = _format_dt(run.created_at)
        lang = (run.language or "—").upper()
        label = f"{summary}  ·  {lang}  ·  {status_label(run.status)}  ·  {created}"
        choices.append((label, run.id))
    return choices


def profile_html(profile: UserProfile | None) -> str:
    if profile is None:
        return ""
    role = escape(profile.role)
    name = escape(profile.full_name)
    email = escape(profile.email)
    return (
        '<div class="profile">'
        f'<div class="avatar">{escape(profile.full_name[:1].upper())}</div>'
        "<div>"
        f'<div class="profile-name">{name}</div>'
        f'<div class="profile-email">{email}</div>'
        f'<span class="badge badge-{role}">{role}</span>'
        "</div></div>"
    )


def roadmap_html() -> str:
    live = [
        ("Level 1 pipeline", "live"),
        ("R1 Identity & Privacy", "live"),
        ("Gradio workspace", "live"),
        ("R2 Safe Execution", "live"),
        ("R6 Evaluation Gate", "live"),
        ("R7 Safe SQL Agent", "live"),
    ]
    next_up = [
        ("R3 Escalation", "next"),
        ("R4 Cost & Latency", "next"),
        ("R5 Resilience", "next"),
    ]
    items = "".join(_roadmap_item(label, state) for label, state in live + next_up)
    return f'<div class="roadmap"><div class="roadmap-title">Roadmap</div>{items}</div>'


def empty_code() -> str:
    return "# No generated code for this run.\n# Unsupported or failed generations leave this empty on purpose.\n"


def empty_tests() -> str:
    return "# No generated tests for this run.\n"


def run_to_dict(run: RunRecord | None) -> dict[str, Any] | None:
    if run is None:
        return None
    return run.model_dump(mode="json")


def run_from_dict(payload: dict[str, Any] | None) -> RunRecord | None:
    if not payload:
        return None
    return RunRecord.model_validate(payload)


def execution_report_json(run: RunRecord) -> dict[str, Any]:
    return {
        "id": run.id,
        "status": run.status,
        "task_type": run.task_type,
        "language": run.language,
        "test_results": run.test_results,
        "execution_time": run.execution_time,
        "artifacts": {
            "status_detail": (run.artifacts or {}).get("status_detail"),
            "exit_code": (run.artifacts or {}).get("exit_code"),
            "timed_out": (run.artifacts or {}).get("timed_out"),
            "error_message": (run.artifacts or {}).get("error_message"),
            "stdout": (run.artifacts or {}).get("stdout"),
            "stderr": (run.artifacts or {}).get("stderr"),
            "generation_successful": (run.artifacts or {}).get("generation_successful"),
            "execution_successful": (run.artifacts or {}).get("execution_successful"),
            "tests_passed": (run.artifacts or {}).get("tests_passed"),
            "policy_decision": (run.artifacts or {}).get("policy_decision"),
            "policy_reasons": (run.artifacts or {}).get("policy_reasons"),
            "approval_status": (run.artifacts or {}).get("approval_status"),
            "sandbox_backend": (run.artifacts or {}).get("sandbox_backend"),
            "idempotency_status": (run.artifacts or {}).get("idempotency_status"),
            "network_isolated": (run.artifacts or {}).get("network_isolated"),
        },
    }


def sql_result_markdown(message: str, columns: list[str], rows: list[list]) -> str:
    """Bounded table. Cell text is escaped and already masked by the service."""
    if not rows:
        if message.startswith("No matching"):
            return message
        return f"{message}\n\n_No rows returned._"
    header = "| " + " | ".join(escape(column) for column in columns) + " |"
    rule = "| " + " | ".join("---" for _ in columns) + " |"
    lines = [header, rule]
    for row in rows[:50]:
        cells = [
            escape("" if value is None else str(value)).replace("|", "\\|").replace("\n", " ")
            for value in row
        ]
        lines.append("| " + " | ".join(cells) + " |")
    return message + "\n\n" + "\n".join(lines)


def tickets_markdown(overview: dict | None, error: str = "") -> str:
    if error:
        return f"**Tickets:** {escape(error)}"
    if not overview:
        return "_No assigned tickets._"
    if not overview.get("r3_connected"):
        return (
            "_No assigned tickets._\n\n"
            "Ticket investigation stays empty until R3 connects an assignment source. "
            "An instructor login does not open every student's history."
        )
    tickets = overview.get("tickets") or []
    if not tickets:
        return "_No tickets are assigned to you._"
    lines = ["### Assigned tickets", ""]
    for ticket in tickets:
        lines.append(
            f"- `{escape(str(ticket.get('ticket_id', '')))}` · "
            f"{escape(str(ticket.get('priority', '')))} · "
            f"{escape(str(ticket.get('sla_status', '')))}\n"
            f"  Student ref `{escape(str(ticket.get('student_ref', '')))}` · "
            f"run `{escape(str(ticket.get('run_id') or ''))}`\n"
            f"  {escape(str(ticket.get('sanitised_request', ''))[:240])}"
        )
    return "\n".join(lines)


def ticket_context_markdown(payload: dict | None, error: str = "") -> str:
    if error:
        return escape(error)
    if not payload:
        return "_No ticket selected._"
    ticket = payload.get("ticket") or {}
    lines = [
        f"**Ticket** `{escape(str(ticket.get('ticket_id', '')))}`",
        f"Priority: {escape(str(ticket.get('priority', '')))}",
        f"Created: {escape(str(ticket.get('created_at', '')))}",
        f"SLA: {escape(str(ticket.get('sla_status', '')))}",
        f"Student ref: `{escape(str(ticket.get('student_ref', '')))}`",
        "",
        escape(str(ticket.get("sanitised_request", ""))),
        "",
        escape(str(ticket.get("handoff_summary", ""))),
        "",
        f"Attempts: {escape(str(ticket.get('attempts', '')))}",
        f"Last failing test: {escape(str(ticket.get('last_failing_test', '')))}",
        "",
        "### Repairs",
    ]
    for repair in payload.get("repairs") or []:
        lines.append(
            f"- `{escape(str(repair.get('run_id', '')))}` · {escape(str(repair.get('status', '')))}"
        )
        code = escape(str(repair.get("generated_code", ""))[:500])
        if code:
            lines.append("")
            lines.append("```python")
            lines.append(code)
            lines.append("```")
    return "\n".join(lines)


def _roadmap_item(label: str, state: str) -> str:
    tag = "Live" if state == "live" else "Upcoming"
    return (
        f'<div class="roadmap-item {state}">'
        f"<span>{escape(label)}</span><span class='tag'>{tag}</span></div>"
    )


def _format_dt(value: datetime) -> str:
    if value.tzinfo is None:
        return value.strftime("%Y-%m-%d %H:%M")
    return value.strftime("%Y-%m-%d %H:%M UTC")
