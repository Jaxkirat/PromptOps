"""Shared helper for invoking an LLM with structured output and uniform error handling."""

from __future__ import annotations

import logging
from typing import TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, ValidationError

from codeforge.exceptions import AgentExecutionError

logger = logging.getLogger(__name__)

TModel = TypeVar("TModel", bound=BaseModel)


def invoke_structured(
    llm: BaseChatModel,
    schema: type[TModel],
    system_prompt: str,
    user_prompt: str,
    agent_name: str,
) -> TModel:
    """Invoke ``llm`` with structured output and return a validated ``schema`` instance.

    Raises:
        AgentExecutionError: if the LLM call fails, returns nothing, or returns
            data that does not validate against ``schema``.
    """
    structured_llm = llm.with_structured_output(schema)
    messages = [SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)]
    try:
        result = structured_llm.invoke(messages)
    except ValidationError as exc:
        raise AgentExecutionError(
            agent_name, f"LLM returned data that failed {schema.__name__} validation: {exc}"
        ) from exc
    except Exception as exc:  # noqa: BLE001 - normalised into a pipeline error
        raise AgentExecutionError(agent_name, f"LLM call failed: {exc}") from exc

    if result is None:
        raise AgentExecutionError(agent_name, "LLM returned an empty response.")

    if isinstance(result, schema):
        return result

    # Some providers return a dict; validate it explicitly.
    try:
        return schema.model_validate(result)
    except ValidationError as exc:
        raise AgentExecutionError(
            agent_name, f"LLM output failed {schema.__name__} validation: {exc}"
        ) from exc
