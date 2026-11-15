"""Which configured model each agent uses. Defaults stay on LLM_MODEL."""

from __future__ import annotations

from codeforge.config.settings import Settings, get_settings

SMALL_AGENTS = frozenset({"router", "requirements", "triage", "handoff", "compaction"})
LARGE_AGENTS = frozenset({"code_generation", "test_generation", "repair"})


def tier_for(agent: str) -> str:
    if agent in SMALL_AGENTS:
        return "small"
    if agent in LARGE_AGENTS:
        return "large"
    return "large"


def model_for(agent: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if tier_for(agent) == "small" and settings.llm_model_small:
        return settings.llm_model_small
    if tier_for(agent) == "large" and settings.llm_model_large:
        return settings.llm_model_large
    return settings.llm_model
