"""Test Generation agent: produces pytest unit tests for the generated code."""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel

from codeforge.agents._base import invoke_structured
from codeforge.exceptions import AgentExecutionError
from codeforge.models.schemas import CodeOutput, RequirementsOutput, TestOutput
from codeforge.prompts.test_generation import (
    TEST_GENERATION_SYSTEM_PROMPT,
    build_test_generation_prompt,
)

logger = logging.getLogger(__name__)


class TestGenerationAgent:
    """Generates executable pytest tests covering requirements and edge cases."""

    name = "test_generation"

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    def run(self, requirements: RequirementsOutput, code: CodeOutput) -> TestOutput:
        """Generate pytest tests and return a validated :class:`TestOutput`."""
        logger.info("Generating tests for function '%s'", requirements.function_name)
        output = invoke_structured(
            llm=self._llm,
            schema=TestOutput,
            system_prompt=TEST_GENERATION_SYSTEM_PROMPT,
            user_prompt=build_test_generation_prompt(
                requirements_json=requirements.model_dump_json(indent=2),
                implementation_code=code.code,
            ),
            agent_name=self.name,
        )
        if not output.test_code.strip():
            raise AgentExecutionError(self.name, "LLM returned empty test code.")
        logger.info("Generated tests with %d described cases", len(output.test_cases))
        return output
