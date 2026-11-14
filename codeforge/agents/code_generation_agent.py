"""Code Generation agent: produces executable implementation code from requirements."""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel

from codeforge.agents._base import invoke_structured
from codeforge.exceptions import AgentExecutionError
from codeforge.models.schemas import CodeOutput, RequirementsOutput
from codeforge.prompts.code_generation import (
    CODE_GENERATION_SYSTEM_PROMPT,
    build_code_generation_prompt,
)

logger = logging.getLogger(__name__)


class CodeGenerationAgent:
    """Generates an executable implementation that satisfies the requirements."""

    name = "code_generation"

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    def run(self, requirements: RequirementsOutput) -> CodeOutput:
        """Generate implementation code and return a validated :class:`CodeOutput`."""
        logger.info("Generating code for function '%s'", requirements.function_name)
        output = invoke_structured(
            llm=self._llm,
            schema=CodeOutput,
            system_prompt=CODE_GENERATION_SYSTEM_PROMPT,
            user_prompt=build_code_generation_prompt(
                requirements.model_dump_json(indent=2)
            ),
            agent_name=self.name,
        )
        if not output.code.strip():
            raise AgentExecutionError(self.name, "LLM returned empty implementation code.")
        logger.info("Generated %d lines of code", output.code.count("\n") + 1)
        return output
