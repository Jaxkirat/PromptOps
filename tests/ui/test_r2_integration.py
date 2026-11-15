"""Gradio-facing R2 presentation and instructor-only approval actions."""

from codeforge.services.run_service import RunRecord
from codeforge.ui.formatters import execution_markdown
from codeforge.ui.handlers import handle_decide_approval, handle_refresh_approvals, new_session
from datetime import datetime, timezone


def _run(status: str, **artifacts) -> RunRecord:
    return RunRecord(
        id="run1",
        sanitised_request="add",
        task_type="python",
        language="python",
        status=status,
        generated_code="def add(a, b):\n    return a + b\n",
        generated_tests="def test_add():\n    assert True\n",
        test_results={"passed": 0, "failed": 0, "skipped": 0, "total": 0, "exit_code": None},
        execution_time=None,
        redaction_count=0,
        created_at=datetime.now(timezone.utc),
        artifacts=artifacts,
    )


def test_execution_tab_shows_policy_and_does_not_claim_the_old_runner():
    paused = execution_markdown(
        _run(
            "awaiting_approval",
            policy_decision="needs_approval",
            policy_reasons=["open() requires human approval."],
            approval_status="pending",
            executed=False,
            tests_passed=False,
        )
    )
    assert "Execution paused: human approval required." in paused
    assert "needs_approval" in paused
    assert "Tests passed: **no**" in paused
    assert "development-grade" not in paused

    denied = execution_markdown(
        _run("denied", policy_decision="deny", executed=False, tests_passed=False, error_message="blocked")
    )
    assert "deny" in denied
    assert "Tests passed: **no**" in denied


def test_student_session_has_no_approval_queue():
    text = handle_refresh_approvals(new_session())
    assert text == ""
    message = handle_decide_approval(new_session(), "abc", "approved", True)
    assert "instructors" in message.lower()
