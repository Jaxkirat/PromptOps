"""Reporting stays honest for every R2 execution status."""

from codeforge.execution.reporter import build_report
from codeforge.models.schemas import CodeOutput, ExecutionResult, RouterOutput, TestOutput


def _state(execution: ExecutionResult) -> dict:
    return {
        "user_request": "add numbers",
        "router_output": RouterOutput(
            task_type="python",
            language="python",
            description="python",
            confidence=0.9,
            reasoning="python",
        ),
        "code_output": CodeOutput(language="python", code="def add(a, b):\n    return a + b\n", explanation=""),
        "test_output": TestOutput(language="python", test_framework="pytest", test_code="def test_x():\n    assert True\n"),
        "execution_result": execution,
    }


def test_passed_requires_a_real_pytest_exit():
    report = build_report(
        _state(ExecutionResult(status="passed", exit_code=0, executed=True, passed_tests=1, total_tests=1))
    )
    assert report.status == "success"
    assert report.tests_passed is True


def test_unexecuted_passed_status_is_not_success():
    report = build_report(_state(ExecutionResult(status="passed", executed=False, exit_code=None)))
    assert report.status != "success"
    assert report.tests_passed is False


def test_denied_rejected_pending_and_unavailable():
    denied = build_report(_state(ExecutionResult(status="denied", executed=False, error_message="blocked")))
    waiting = build_report(_state(ExecutionResult(status="awaiting_approval", executed=False)))
    rejected = build_report(_state(ExecutionResult(status="rejected", executed=False)))
    missing = build_report(_state(ExecutionResult(status="unavailable", executed=False, error_message="down")))
    assert denied.status == "denied"
    assert waiting.status == "awaiting_approval"
    assert rejected.status == "rejected"
    assert missing.status == "unavailable"
    assert denied.tests_passed is False
    assert "passed" not in denied.status_detail.lower() or "not" in denied.status_detail.lower()
