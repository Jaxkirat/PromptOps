"""Schema validation tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from codeforge.models.schemas import (
    CodeOutput,
    ExecutionResult,
    FinalReport,
    RouterOutput,
    TestOutput,
    strip_markdown_fences,
)


class TestRouterOutput:
    def test_valid(self) -> None:
        output = RouterOutput(
            task_type="python",
            language="python",
            description="desc",
            confidence=0.9,
            reasoning="because",
        )
        assert output.task_type == "python"

    def test_invalid_task_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RouterOutput(
                task_type="javascript",  # type: ignore[arg-type]
                language="javascript",
                description="desc",
                confidence=0.9,
                reasoning="because",
            )

    @pytest.mark.parametrize("confidence", [-0.1, 1.1])
    def test_confidence_bounds(self, confidence: float) -> None:
        with pytest.raises(ValidationError):
            RouterOutput(
                task_type="python",
                language="python",
                description="desc",
                confidence=confidence,
                reasoning="because",
            )


class TestFenceStripping:
    def test_strip_fenced_code(self) -> None:
        fenced = "```python\ndef f():\n    return 1\n```"
        assert strip_markdown_fences(fenced) == "def f():\n    return 1"

    def test_plain_code_untouched(self) -> None:
        code = "def f():\n    return 1"
        assert strip_markdown_fences(code) == code

    def test_code_output_strips_fences(self) -> None:
        output = CodeOutput(language="python", code="```python\nx = 1\n```")
        assert output.code == "x = 1"

    def test_test_output_strips_fences(self) -> None:
        output = TestOutput(
            language="python",
            test_framework="pytest",
            test_code="```\ndef test_x():\n    assert True\n```",
        )
        assert output.test_code == "def test_x():\n    assert True"


class TestExecutionResult:
    def test_defaults(self) -> None:
        result = ExecutionResult(status="not_run")
        assert result.total_tests == 0
        assert result.timed_out is False
        assert result.exit_code is None

    def test_negative_counts_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ExecutionResult(status="passed", passed_tests=-1)


class TestFinalReport:
    def test_minimal_report(self) -> None:
        report = FinalReport(user_request="req", status="unsupported")
        assert report.generation_successful is False
        assert report.tests_passed is False

    def test_invalid_status_rejected(self) -> None:
        with pytest.raises(ValidationError):
            FinalReport(user_request="req", status="great")  # type: ignore[arg-type]
