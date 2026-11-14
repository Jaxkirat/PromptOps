"""Execution runner tests using known safe sample code (no LLM involved)."""

from __future__ import annotations

import dataclasses

from codeforge.config.settings import Settings
from codeforge.execution.runner import PytestRunner


def _settings(timeout: int = 30) -> Settings:
    return Settings(
        llm_provider="openai",
        llm_model="gpt-4.1-mini",
        llm_api_key="",
        llm_base_url="",
        openai_api_key="",
        anthropic_api_key="",
        google_api_key="",
        app_env="test",
        log_level="INFO",
        execution_timeout_seconds=timeout,
        max_test_output_length=10000,
    )


PASSING_CODE = """\
def add(a: int, b: int) -> int:
    return a + b
"""

PASSING_TESTS = """\
from solution import add


def test_add_positive():
    assert add(1, 2) == 3


def test_add_negative():
    assert add(-1, -2) == -3


def test_add_zero():
    assert add(0, 0) == 0
"""

FAILING_TESTS = """\
from solution import add


def test_add_correct():
    assert add(1, 2) == 3


def test_add_wrong_expectation():
    assert add(1, 2) == 99
"""

SYNTAX_ERROR_CODE = """\
def broken(:
    return
"""

SLOW_TESTS = """\
import time

from solution import add


def test_slow():
    time.sleep(30)
    assert add(1, 1) == 2
"""


class TestPytestRunner:
    def test_passing_tests(self) -> None:
        result = PytestRunner(_settings()).run(PASSING_CODE, PASSING_TESTS)
        assert result.status == "passed"
        assert result.exit_code == 0
        assert result.total_tests == 3
        assert result.passed_tests == 3
        assert result.failed_tests == 0
        assert result.timed_out is False
        assert result.execution_time_seconds > 0

    def test_failing_tests(self) -> None:
        result = PytestRunner(_settings()).run(PASSING_CODE, FAILING_TESTS)
        assert result.status == "failed"
        assert result.exit_code == 1
        assert result.passed_tests == 1
        assert result.failed_tests == 1
        assert result.error_message is not None

    def test_syntax_error_in_code(self) -> None:
        result = PytestRunner(_settings()).run(SYNTAX_ERROR_CODE, PASSING_TESTS)
        assert result.status == "error"
        assert result.exit_code not in (0, None)
        assert result.passed_tests == 0

    def test_timeout(self) -> None:
        result = PytestRunner(_settings(timeout=3)).run(PASSING_CODE, SLOW_TESTS)
        assert result.status == "timeout"
        assert result.timed_out is True
        assert result.exit_code is None
        assert "timeout" in (result.error_message or "").lower()

    def test_no_tests_collected(self) -> None:
        result = PytestRunner(_settings()).run(PASSING_CODE, "# no tests here\n")
        assert result.status == "error"
        assert "no tests" in (result.error_message or "").lower()

    def test_output_truncation(self) -> None:
        settings = dataclasses.replace(_settings(), max_test_output_length=100)
        result = PytestRunner(settings).run(PASSING_CODE, PASSING_TESTS)
        assert len(result.stdout) <= 100 + len(
            "\n... [output truncated at 100 characters]"
        )
        assert "truncated" in result.stdout
