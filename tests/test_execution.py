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
        jwt_secret_key="",
        jwt_algorithm="HS256",
        access_token_expire_minutes=30,
        database_url="sqlite:///:memory:",
        max_runs_per_user_per_day=20,
        api_host="127.0.0.1",
        api_port=8000,
        cors_allowed_origins=(),
        initial_instructor_email="",
        initial_instructor_password="",
        initial_instructor_name="",
        app_base_url="http://127.0.0.1:8000",
        invite_expiry_hours=72,
        sandbox_backend="restricted-process",
        sandbox_image="codeforge-sandbox:latest",
        sandbox_timeout_seconds=10,
        sandbox_memory_mb=256,
        sandbox_cpu_limit="1",
        sandbox_pids_limit=32,
        sandbox_max_output_bytes=1048576,
        approval_expiry_minutes=60,
        checkpoint_path=":memory:",
        sql_agent_enabled=True,
        sql_max_rows=500,
        sql_default_limit=100,
        sql_timeout_seconds=2.0,
        sql_max_result_bytes=200000,
        sql_max_columns=16,
        sql_dialect="sqlite",
        sql_sample_database="./data/r7_sample.sqlite",
        sql_proposer="fixture",
        llm_model_small="",
        llm_model_large="",
        primary_llm_provider="",
        groq_api_key="",
        groq_model="",
        fallback_1_provider="openai",
        openai_model="gpt-4o-mini",
        fallback_2_provider="",
        fallback_2_api_key="",
        fallback_2_model="",
        llm_max_retries=3,
        llm_retry_base_delay=0.0,
        llm_retry_max_delay=0.0,
        llm_circuit_breaker_threshold=5,
        llm_circuit_breaker_cooldown=30,
        chaos_enabled=False,
        chaos_failure_rate=0.6,
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
