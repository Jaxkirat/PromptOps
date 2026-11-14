"""LangGraph node implementations.

Each node wraps exactly one agent (or the runner/reporter) and returns a
partial state update. Agent failures are captured into ``error`` /
``error_stage`` so the graph can route to the report node instead of crashing.
"""

from __future__ import annotations

import logging

from codeforge.agents.code_generation_agent import CodeGenerationAgent
from codeforge.agents.requirements_agent import RequirementsAgent
from codeforge.agents.router_agent import RouterAgent
from codeforge.agents.test_generation_agent import TestGenerationAgent
from codeforge.exceptions import CodeForgeError
from codeforge.execution.reporter import build_report
from codeforge.execution.runner import PytestRunner
from codeforge.graph.state import CodeForgeState

logger = logging.getLogger(__name__)


class GraphNodes:
    """Bundles the node callables with their agent/runner dependencies."""

    def __init__(
        self,
        router_agent: RouterAgent,
        requirements_agent: RequirementsAgent,
        code_generation_agent: CodeGenerationAgent,
        test_generation_agent: TestGenerationAgent,
        runner: PytestRunner,
    ) -> None:
        self._router = router_agent
        self._requirements = requirements_agent
        self._code_generation = code_generation_agent
        self._test_generation = test_generation_agent
        self._runner = runner

    # -- Agent nodes -------------------------------------------------------

    def router_node(self, state: CodeForgeState) -> CodeForgeState:
        try:
            return {"router_output": self._router.run(state["user_request"])}
        except CodeForgeError as exc:
            return _failure("router", exc)

    def requirements_node(self, state: CodeForgeState) -> CodeForgeState:
        try:
            router_output = state["router_output"]
            assert router_output is not None
            return {
                "requirements_output": self._requirements.run(
                    state["user_request"], router_output
                )
            }
        except CodeForgeError as exc:
            return _failure("requirements", exc)

    def code_generation_node(self, state: CodeForgeState) -> CodeForgeState:
        try:
            requirements = state["requirements_output"]
            assert requirements is not None
            return {"code_output": self._code_generation.run(requirements)}
        except CodeForgeError as exc:
            return _failure("code_generation", exc)

    def test_generation_node(self, state: CodeForgeState) -> CodeForgeState:
        try:
            requirements = state["requirements_output"]
            code = state["code_output"]
            assert requirements is not None and code is not None
            return {"test_output": self._test_generation.run(requirements, code)}
        except CodeForgeError as exc:
            return _failure("test_generation", exc)

    # -- Execution node ----------------------------------------------------
    # NOTE: a future R2 policy gate will be inserted between test generation
    # and this node; keep execution behind the PytestRunner interface.

    def execution_node(self, state: CodeForgeState) -> CodeForgeState:
        code = state["code_output"]
        tests = state["test_output"]
        assert code is not None and tests is not None
        try:
            return {"execution_result": self._runner.run(code.code, tests.test_code)}
        except Exception as exc:  # noqa: BLE001 - runner failures become state
            logger.exception("Execution runner raised unexpectedly")
            return _failure("execution", exc)

    # -- Report node -------------------------------------------------------

    def report_node(self, state: CodeForgeState) -> CodeForgeState:
        return {"report": build_report(state)}


def _failure(stage: str, exc: Exception) -> CodeForgeState:
    logger.error("Stage '%s' failed: %s", stage, exc)
    return {"error": str(exc), "error_stage": stage}
