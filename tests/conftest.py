"""Shared test fixtures: fake LLMs and canned structured outputs.

No live API calls happen in this test suite. The FakeStructuredLLM mimics the
only LLM surface the agents use: ``with_structured_output(schema).invoke(...)``.
"""

from __future__ import annotations

from typing import Any

import pytest

from codeforge.models.schemas import (
    CodeOutput,
    ParameterSpec,
    RequirementsOutput,
    RouterOutput,
    TestOutput,
)


class _FakeStructuredRunnable:
    def __init__(self, response: Any) -> None:
        self._response = response

    def invoke(self, _input: Any, **_kwargs: Any) -> Any:
        if isinstance(self._response, Exception):
            raise self._response
        return self._response


class FakeStructuredLLM:
    """Fake chat model returning canned responses keyed by output schema.

    A response may also be an Exception instance, which will be raised on
    invoke to simulate API failures.
    """

    def __init__(self, responses: dict[type, Any]) -> None:
        self._responses = responses
        self.calls: list[type] = []

    def with_structured_output(self, schema: type, **_kwargs: Any) -> _FakeStructuredRunnable:
        self.calls.append(schema)
        if schema not in self._responses:
            raise AssertionError(f"FakeStructuredLLM has no response for {schema.__name__}")
        return _FakeStructuredRunnable(self._responses[schema])


# ---------------------------------------------------------------------------
# Canned outputs for the flagship scenario:
# "If I pass a list, return its sum using a list comprehension;
#  if a tuple, use functional programming."
# ---------------------------------------------------------------------------

SUM_IMPLEMENTATION = '''\
from functools import reduce
from typing import Union


def sum_elements(values: Union[list, tuple]) -> Union[int, float]:
    """Sum the elements of a list (list comprehension) or tuple (functional style).

    Raises:
        TypeError: if ``values`` is neither a list nor a tuple.
    """
    if isinstance(values, list):
        return sum([item for item in values])
    if isinstance(values, tuple):
        return reduce(lambda acc, item: acc + item, values, 0)
    raise TypeError("values must be a list or a tuple")
'''

SUM_TESTS = '''\
import inspect

import pytest

from solution import sum_elements


def test_list_normal():
    assert sum_elements([1, 2, 3]) == 6


def test_tuple_normal():
    assert sum_elements((4, 5, 6)) == 15


def test_empty_list():
    assert sum_elements([]) == 0


def test_empty_tuple():
    assert sum_elements(()) == 0


def test_single_element_list():
    assert sum_elements([7]) == 7


def test_negative_numbers():
    assert sum_elements([-1, -2, 3]) == 0


def test_invalid_type_raises():
    with pytest.raises(TypeError):
        sum_elements("not a sequence")


def test_list_branch_uses_list_comprehension():
    source = inspect.getsource(sum_elements)
    assert "for" in source and "[" in source


def test_tuple_branch_uses_functional_programming():
    source = inspect.getsource(sum_elements)
    assert "reduce" in source or "map" in source
'''


@pytest.fixture
def router_python_output() -> RouterOutput:
    return RouterOutput(
        task_type="python",
        language="python",
        description="Sum a list with a list comprehension or a tuple functionally.",
        confidence=0.95,
        reasoning="The request describes a Python coding task with no other language.",
    )


@pytest.fixture
def router_sql_output() -> RouterOutput:
    return RouterOutput(
        task_type="sql",
        language="sql",
        description="Write an SQL query for top customers.",
        confidence=0.97,
        reasoning="The user explicitly asked for an SQL query.",
    )


@pytest.fixture
def router_other_output() -> RouterOutput:
    return RouterOutput(
        task_type="other",
        language="none",
        description="A general knowledge question, not a programming task.",
        confidence=0.99,
        reasoning="The request does not ask for any code.",
    )


@pytest.fixture
def requirements_output() -> RequirementsOutput:
    return RequirementsOutput(
        task_type="python",
        language="python",
        function_name="sum_elements",
        description="Sum the elements of a list or tuple with constrained styles.",
        parameters=[
            ParameterSpec(
                name="values",
                data_type="list | tuple",
                description="Sequence of numbers to sum.",
                required=True,
            )
        ],
        return_type="int | float",
        expected_behavior=[
            "A list input returns the sum of its elements.",
            "A tuple input returns the sum of its elements.",
        ],
        edge_cases=["Empty list returns 0.", "Empty tuple returns 0."],
        constraints=[
            "List input must be summed using a list comprehension.",
            "Tuple input must be summed using functional programming.",
        ],
        implementation_notes=["Assumption: non-list/tuple input raises TypeError."],
    )


@pytest.fixture
def code_output() -> CodeOutput:
    return CodeOutput(
        language="python",
        code=SUM_IMPLEMENTATION,
        explanation="Branches on input type; list comprehension vs functools.reduce.",
        dependencies=[],
        implementation_notes=[],
    )


@pytest.fixture
def test_output() -> TestOutput:
    return TestOutput(
        language="python",
        test_framework="pytest",
        test_code=SUM_TESTS,
        test_cases=[
            "list normal input",
            "tuple normal input",
            "empty list",
            "empty tuple",
            "single element",
            "negative numbers",
            "invalid type raises TypeError",
            "list comprehension constraint",
            "functional programming constraint",
        ],
    )


# ---------------------------------------------------------------------------
# R1 (Phase 2) fixtures: isolated test database, app factory, fake pipeline.
# ---------------------------------------------------------------------------

TEST_JWT_SECRET = "unit-test-jwt-secret-key-0123456789-abcdefghijklmnop"


class FakePipeline:
    """Deterministic stand-in for the LangGraph pipeline.

    Records every input it receives so tests can verify that ONLY sanitized
    text ever reaches the pipeline/LLM, and counts invocations so quota tests
    can prove the graph is never called after a rejection.
    """

    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, text: str) -> dict:
        from codeforge.models.schemas import ExecutionResult, FinalReport

        self.calls.append(text)
        report = FinalReport(
            user_request=text,
            status="success",
            status_detail="All 3 generated tests passed in actual pytest execution.",
            task_type="python",
            language="python",
            router_output=RouterOutput(
                task_type="python",
                language="python",
                description="Python function generation request.",
                confidence=0.97,
                reasoning="Clearly a Python coding task.",
            ),
            requirements=RequirementsOutput(
                task_type="python",
                language="python",
                function_name="solution",
                description="Return 42.",
                parameters=[ParameterSpec(name="value", data_type="object", description="input")],
                return_type="int",
                expected_behavior=["returns 42"],
                edge_cases=[],
                constraints=[],
            ),
            code=CodeOutput(
                language="python",
                code="def solution():\n    return 42\n",
                explanation="Constant function used by the test double.",
            ),
            tests=TestOutput(
                language="python",
                test_framework="pytest",
                test_code="from solution import solution\n\ndef test_solution():\n    assert solution() == 42\n",
            ),
            execution=ExecutionResult(
                status="passed",
                exit_code=0,
                total_tests=3,
                passed_tests=3,
                failed_tests=0,
                execution_time_seconds=0.1,
                stdout="3 passed",
                stderr="",
            ),
            generation_successful=True,
            execution_successful=True,
            tests_passed=True,
        )
        return {"user_request": text, "report": report}


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    """Isolated settings + temporary database for R1 tests."""
    from codeforge.config.settings import get_settings
    from codeforge.database.database import init_db, reset_database_state

    db_path = tmp_path / "test_codeforge.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path.as_posix()}")
    monkeypatch.setenv("JWT_SECRET_KEY", TEST_JWT_SECRET)
    monkeypatch.setenv("JWT_ALGORITHM", "HS256")
    monkeypatch.setenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30")
    monkeypatch.setenv("MAX_RUNS_PER_USER_PER_DAY", "20")
    monkeypatch.setenv("INITIAL_INSTRUCTOR_EMAIL", "")
    monkeypatch.setenv("INITIAL_INSTRUCTOR_PASSWORD", "")
    get_settings.cache_clear()
    reset_database_state()
    init_db()
    yield
    reset_database_state()
    get_settings.cache_clear()


@pytest.fixture
def fake_pipeline(api_env):
    """Install a recording fake pipeline for the duration of a test."""
    from codeforge.services.run_service import set_pipeline_runner

    pipeline = FakePipeline()
    set_pipeline_runner(pipeline)
    yield pipeline
    set_pipeline_runner(None)


@pytest.fixture
def client(api_env, fake_pipeline):
    """FastAPI TestClient over a freshly assembled application."""
    from fastapi.testclient import TestClient

    from codeforge.api.main import create_application

    with TestClient(create_application()) as test_client:
        yield test_client


def register_and_login(client, email: str, password: str = "StrongPassword123") -> str:
    """Helper: register a student and return a bearer token."""
    response = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Test User"},
    )
    assert response.status_code == 201, response.text
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def r2_execution_defaults(monkeypatch, tmp_path):
    """Keep the existing suite on an explicit non-isolating backend.

    Production default remains Docker, which fails closed when the daemon is
    down. These tests opt into restricted-process so safe canned code still
    runs pytest. Approval-class code is refused by that backend.
    """
    from codeforge.config.settings import get_settings
    from codeforge.graph import workflow as workflow_module

    monkeypatch.setenv("CODEFORGE_SANDBOX_BACKEND", "restricted-process")
    monkeypatch.setenv("CODEFORGE_CHECKPOINT_PATH", str(tmp_path / "checkpoints.sqlite"))
    get_settings.cache_clear()
    workflow_module._checkpointer = None
    workflow_module._checkpointer_path = None
    from codeforge.sql_agent.proposer import set_sql_proposer
    from codeforge.sql_agent.tickets import set_ticket_access

    set_sql_proposer(None)
    set_ticket_access(None)
    yield
    set_sql_proposer(None)
    set_ticket_access(None)
    get_settings.cache_clear()
    workflow_module._checkpointer = None
    workflow_module._checkpointer_path = None


@pytest.fixture
def fake_llm_full_pipeline(
    router_python_output: RouterOutput,
    requirements_output: RequirementsOutput,
    code_output: CodeOutput,
    test_output: TestOutput,
) -> FakeStructuredLLM:
    """Fake LLM that successfully drives the entire python pipeline."""
    return FakeStructuredLLM(
        {
            RouterOutput: router_python_output,
            RequirementsOutput: requirements_output,
            CodeOutput: code_output,
            TestOutput: test_output,
        }
    )
