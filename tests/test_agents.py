"""Agent tests with mocked LLMs (no live API calls)."""

from __future__ import annotations

import pytest

from codeforge.agents.code_generation_agent import CodeGenerationAgent
from codeforge.agents.requirements_agent import RequirementsAgent
from codeforge.agents.router_agent import RouterAgent
from codeforge.agents.test_generation_agent import TestGenerationAgent
from codeforge.exceptions import AgentExecutionError
from codeforge.models.schemas import (
    CodeOutput,
    RequirementsOutput,
    RouterOutput,
    TestOutput,
)
from tests.conftest import FakeStructuredLLM


class TestRouterAgent:
    def test_returns_validated_output(self, router_python_output: RouterOutput) -> None:
        llm = FakeStructuredLLM({RouterOutput: router_python_output})
        result = RouterAgent(llm).run("sum a list")  # type: ignore[arg-type]
        assert isinstance(result, RouterOutput)
        assert result.task_type == "python"

    def test_llm_failure_raises_agent_error(self) -> None:
        llm = FakeStructuredLLM({RouterOutput: RuntimeError("rate limit exceeded")})
        with pytest.raises(AgentExecutionError, match="router"):
            RouterAgent(llm).run("sum a list")  # type: ignore[arg-type]

    def test_empty_response_raises_agent_error(self) -> None:
        llm = FakeStructuredLLM({RouterOutput: None})
        with pytest.raises(AgentExecutionError, match="empty"):
            RouterAgent(llm).run("sum a list")  # type: ignore[arg-type]

    def test_dict_response_is_validated(self) -> None:
        raw = {
            "task_type": "python",
            "language": "python",
            "description": "d",
            "confidence": 0.8,
            "reasoning": "r",
        }
        llm = FakeStructuredLLM({RouterOutput: raw})
        result = RouterAgent(llm).run("sum a list")  # type: ignore[arg-type]
        assert isinstance(result, RouterOutput)

    def test_malformed_dict_raises_agent_error(self) -> None:
        llm = FakeStructuredLLM({RouterOutput: {"task_type": "python"}})
        with pytest.raises(AgentExecutionError, match="validation"):
            RouterAgent(llm).run("sum a list")  # type: ignore[arg-type]


class TestRequirementsAgent:
    def test_returns_validated_output(
        self,
        router_python_output: RouterOutput,
        requirements_output: RequirementsOutput,
    ) -> None:
        llm = FakeStructuredLLM({RequirementsOutput: requirements_output})
        result = RequirementsAgent(llm).run("request", router_python_output)  # type: ignore[arg-type]
        assert isinstance(result, RequirementsOutput)
        assert result.function_name == "sum_elements"

    def test_constraints_are_preserved(
        self,
        router_python_output: RouterOutput,
        requirements_output: RequirementsOutput,
    ) -> None:
        llm = FakeStructuredLLM({RequirementsOutput: requirements_output})
        result = RequirementsAgent(llm).run("request", router_python_output)  # type: ignore[arg-type]
        constraints = " ".join(result.constraints).lower()
        assert "list comprehension" in constraints
        assert "functional" in constraints


class TestCodeGenerationAgent:
    def test_returns_validated_output(
        self, requirements_output: RequirementsOutput, code_output: CodeOutput
    ) -> None:
        llm = FakeStructuredLLM({CodeOutput: code_output})
        result = CodeGenerationAgent(llm).run(requirements_output)  # type: ignore[arg-type]
        assert isinstance(result, CodeOutput)
        assert "def sum_elements" in result.code
        assert "```" not in result.code

    def test_empty_code_raises(self, requirements_output: RequirementsOutput) -> None:
        empty = CodeOutput(language="python", code="   \n")
        llm = FakeStructuredLLM({CodeOutput: empty})
        with pytest.raises(AgentExecutionError, match="empty implementation"):
            CodeGenerationAgent(llm).run(requirements_output)  # type: ignore[arg-type]


class TestTestGenerationAgent:
    def test_returns_validated_output(
        self,
        requirements_output: RequirementsOutput,
        code_output: CodeOutput,
        test_output: TestOutput,
    ) -> None:
        llm = FakeStructuredLLM({TestOutput: test_output})
        result = TestGenerationAgent(llm).run(requirements_output, code_output)  # type: ignore[arg-type]
        assert isinstance(result, TestOutput)
        assert result.test_framework == "pytest"
        assert "from solution import" in result.test_code

    def test_empty_tests_raise(
        self, requirements_output: RequirementsOutput, code_output: CodeOutput
    ) -> None:
        empty = TestOutput(language="python", test_framework="pytest", test_code=" ")
        llm = FakeStructuredLLM({TestOutput: empty})
        with pytest.raises(AgentExecutionError, match="empty test code"):
            TestGenerationAgent(llm).run(requirements_output, code_output)  # type: ignore[arg-type]
