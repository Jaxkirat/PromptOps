"""Requirements Extraction agent: turns a request into structured requirements."""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel

from codeforge.agents._base import invoke_structured
from codeforge.models.schemas import RequirementsOutput, RouterOutput
from codeforge.prompts.requirements import (
    REQUIREMENTS_SYSTEM_PROMPT,
    build_requirements_prompt,
)

logger = logging.getLogger(__name__)


class RequirementsAgent:
    """Extracts precise, structured programming requirements from the user request."""

    name = "requirements"

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    def run(self, user_request: str, router_output: RouterOutput) -> RequirementsOutput:
        """Extract requirements for ``user_request`` and return a validated model."""
        logger.info("Extracting requirements for a %s task", router_output.task_type)
        output = invoke_structured(
            llm=self._llm,
            schema=RequirementsOutput,
            system_prompt=REQUIREMENTS_SYSTEM_PROMPT,
            user_prompt=build_requirements_prompt(
                user_request=user_request,
                router_description=router_output.description,
                language=router_output.language,
            ),
            agent_name=self.name,
        )
        logger.info(
            "Extracted requirements: function=%s constraints=%d",
            output.function_name,
            len(output.constraints),
        )
        return output
