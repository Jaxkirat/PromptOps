"""Router / Parser agent: classifies the incoming natural-language request."""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel

from codeforge.agents._base import invoke_structured
from codeforge.models.schemas import RouterOutput
from codeforge.prompts.router import ROUTER_SYSTEM_PROMPT, build_router_prompt

logger = logging.getLogger(__name__)


class RouterAgent:
    """Classifies a user request as a python, sql, or other task."""

    name = "router"

    def __init__(self, llm: BaseChatModel) -> None:
        self._llm = llm

    def run(self, user_request: str) -> RouterOutput:
        """Classify ``user_request`` and return a validated :class:`RouterOutput`."""
        logger.info("Routing request (%d chars)", len(user_request))
        output = invoke_structured(
            llm=self._llm,
            schema=RouterOutput,
            system_prompt=ROUTER_SYSTEM_PROMPT,
            user_prompt=build_router_prompt(user_request),
            agent_name=self.name,
        )
        logger.info(
            "Routed as task_type=%s language=%s confidence=%.2f",
            output.task_type,
            output.language,
            output.confidence,
        )
        return output
