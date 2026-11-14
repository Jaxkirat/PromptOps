"""End-to-end integration tests with mocked LLMs and REAL pytest execution.

The LLM is faked (no API calls), but generated code and tests run through the
real subprocess-based execution runner, so the final report reflects actual
pytest results.
"""

from __future__ import annotations

from codeforge.graph.workflow import run_codeforge
from codeforge.models.schemas import (
    CodeOutput,
    ParameterSpec,
    RequirementsOutput,
    RouterOutput,
    TestOutput,
)
from tests.conftest import FakeStructuredLLM


def _python_pipeline_llm(
    function_name: str, description: str, code: str, tests: str
) -> FakeStructuredLLM:
    """Build a fake LLM driving the full python pipeline for one scenario."""
    return FakeStructuredLLM(
        {
            RouterOutput: RouterOutput(
                task_type="python",
                language="python",
                description=description,
                confidence=0.95,
                reasoning="Clearly a Python coding task.",
            ),
            RequirementsOutput: RequirementsOutput(
                task_type="python",
                language="python",
                function_name=function_name,
                description=description,
                parameters=[
                    ParameterSpec(name="value", data_type="object", description="input")
                ],
                return_type="object",
                expected_behavior=[description],
            ),
            CodeOutput: CodeOutput(language="python", code=code),
            TestOutput: TestOutput(
                language="python",
                test_framework="pytest",
                test_code=tests,
                test_cases=["generated scenario tests"],
            ),
        }
    )


class TestFlagshipScenario:
    """'If I pass a list, return its sum using a list comprehension;
    if a tuple, use functional programming.'"""

    REQUEST = (
        "If I pass a list, return its sum using a list comprehension; "
        "if a tuple, use functional programming."
    )

    def test_full_pipeline_with_real_execution(self, fake_llm_full_pipeline) -> None:
        result = run_codeforge(self.REQUEST, llm=fake_llm_full_pipeline)
        report = result["report"]

        # Python task detected and requirements extracted.
        assert report.task_type == "python"
        constraints = " ".join(report.requirements.constraints).lower()
        assert "list comprehension" in constraints
        assert "functional" in constraints

        # Implementation honours both constraints.
        assert "[item for item in values]" in report.code.code  # list comprehension
        assert "reduce" in report.code.code  # functional programming

        # Tests were generated and ACTUALLY executed via pytest.
        assert report.tests.test_framework == "pytest"
        execution = report.execution
        assert execution is not None
        assert execution.exit_code == 0
        assert execution.total_tests == 9
        assert execution.passed_tests == 9
        assert execution.failed_tests == 0

        # Report reflects the real pytest outcome.
        assert report.status == "success"
        assert report.generation_successful is True
        assert report.execution_successful is True
        assert report.tests_passed is True


class TestPalindromeScenario:
    CODE = '''\
def is_palindrome(text: str) -> bool:
    """Return True if ``text`` reads the same forwards and backwards."""
    normalized = text.lower()
    return normalized == normalized[::-1]
'''

    TESTS = """\
from solution import is_palindrome


def test_simple_palindrome():
    assert is_palindrome("racecar") is True


def test_not_palindrome():
    assert is_palindrome("python") is False


def test_empty_string():
    assert is_palindrome("") is True


def test_single_character():
    assert is_palindrome("a") is True


def test_case_insensitive():
    assert is_palindrome("Level") is True
"""

    def test_palindrome_pipeline(self) -> None:
        llm = _python_pipeline_llm(
            "is_palindrome", "Check whether a string is a palindrome.", self.CODE, self.TESTS
        )
        report = run_codeforge("Check whether a string is a palindrome", llm=llm)["report"]
        assert report.status == "success"
        assert report.execution.passed_tests == 5


class TestFactorialScenario:
    CODE = '''\
def factorial(n: int) -> int:
    """Return n! for a non-negative integer n."""
    if n < 0:
        raise ValueError("n must be non-negative")
    result = 1
    for i in range(2, n + 1):
        result *= i
    return result
'''

    TESTS = """\
import pytest

from solution import factorial


def test_factorial_zero():
    assert factorial(0) == 1


def test_factorial_one():
    assert factorial(1) == 1


def test_factorial_five():
    assert factorial(5) == 120


def test_factorial_negative_raises():
    with pytest.raises(ValueError):
        factorial(-1)
"""

    def test_factorial_pipeline(self) -> None:
        llm = _python_pipeline_llm(
            "factorial", "Compute the factorial of an integer.", self.CODE, self.TESTS
        )
        report = run_codeforge("Compute the factorial of a number", llm=llm)["report"]
        assert report.status == "success"
        assert report.execution.passed_tests == 4


class TestFibonacciScenario:
    CODE = '''\
def fibonacci(n: int) -> list[int]:
    """Return the first n Fibonacci numbers."""
    if n < 0:
        raise ValueError("n must be non-negative")
    sequence: list[int] = []
    a, b = 0, 1
    for _ in range(n):
        sequence.append(a)
        a, b = b, a + b
    return sequence
'''

    TESTS = """\
import pytest

from solution import fibonacci


def test_fibonacci_zero():
    assert fibonacci(0) == []


def test_fibonacci_one():
    assert fibonacci(1) == [0]


def test_fibonacci_seven():
    assert fibonacci(7) == [0, 1, 1, 2, 3, 5, 8]


def test_fibonacci_negative_raises():
    with pytest.raises(ValueError):
        fibonacci(-5)
"""

    def test_fibonacci_pipeline(self) -> None:
        llm = _python_pipeline_llm(
            "fibonacci", "Return the first n Fibonacci numbers.", self.CODE, self.TESTS
        )
        report = run_codeforge("Return the first n Fibonacci numbers", llm=llm)["report"]
        assert report.status == "success"
        assert report.execution.passed_tests == 4


class TestSqlScenario:
    def test_sql_identified_but_honestly_not_implemented(
        self, router_sql_output: RouterOutput
    ) -> None:
        llm = FakeStructuredLLM({RouterOutput: router_sql_output})
        report = run_codeforge("Write an SQL query for top customers", llm=llm)["report"]
        assert report.task_type == "sql"
        assert report.status == "unsupported"
        assert "not implemented" in report.status_detail.lower()
        # Nothing was generated or executed.
        assert report.code is None
        assert report.tests is None
        assert report.execution is None
        assert report.tests_passed is False


class TestNonCodingScenario:
    def test_non_coding_request_not_treated_as_python(
        self, router_other_output: RouterOutput
    ) -> None:
        llm = FakeStructuredLLM({RouterOutput: router_other_output})
        report = run_codeforge("What is the capital of France?", llm=llm)["report"]
        assert report.status == "unsupported"
        assert report.task_type == "other"
        assert report.code is None
        assert report.execution is None


class TestFailingGeneratedTests:
    """A report must reflect real failures — never claim success."""

    BAD_CODE = """\
def add(a: int, b: int) -> int:
    return a - b  # intentional bug
"""

    TESTS = """\
from solution import add


def test_add():
    assert add(2, 3) == 5
"""

    def test_failing_tests_reported_honestly(self) -> None:
        llm = _python_pipeline_llm("add", "Add two numbers.", self.BAD_CODE, self.TESTS)
        report = run_codeforge("Add two numbers", llm=llm)["report"]
        assert report.status == "tests_failed"
        assert report.generation_successful is True
        assert report.execution_successful is True  # pytest ran fine
        assert report.tests_passed is False
        assert report.execution.failed_tests == 1
