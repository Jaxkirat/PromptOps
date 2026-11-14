"""Provider-agnostic LLM factory.

All chat-model initialisation lives here. Agents receive an already-built
``BaseChatModel`` instance, so adding a provider (or a future model cascade,
R4) never requires touching agent code.
"""

from __future__ import annotations

import logging

from langchain_core.language_models.chat_models import BaseChatModel

from codeforge.config.settings import Settings, get_settings
from codeforge.exceptions import ConfigurationError

logger = logging.getLogger(__name__)

SUPPORTED_PROVIDERS = ("openai", "anthropic", "google")


def validate_llm_config(settings: Settings | None = None) -> None:
    """Fail fast with a clear message if the LLM configuration is incomplete."""
    settings = settings or get_settings()
    provider = settings.llm_provider.lower()

    if provider not in SUPPORTED_PROVIDERS:
        raise ConfigurationError(
            f"Unsupported LLM_PROVIDER '{settings.llm_provider}'. "
            f"Supported providers: {', '.join(SUPPORTED_PROVIDERS)}."
        )

    if not settings.resolve_api_key():
        provider_var = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "google": "GOOGLE_API_KEY",
        }[provider]
        raise ConfigurationError(
            f"No API key configured for provider '{provider}'. "
            f"Set LLM_API_KEY or {provider_var} in your .env file "
            "(see .env.example for the full list of options)."
        )

    if not settings.llm_model:
        raise ConfigurationError("LLM_MODEL must not be empty.")


def create_llm(settings: Settings | None = None) -> BaseChatModel:
    """Create the chat model configured via environment variables.

    Only the selected provider's credentials are required. The returned model
    is deterministic (temperature 0) because the pipeline needs reproducible
    structured outputs.
    """
    settings = settings or get_settings()
    validate_llm_config(settings)

    provider = settings.llm_provider.lower()
    api_key = settings.resolve_api_key()
    logger.info("Initialising LLM provider=%s model=%s", provider, settings.llm_model)

    if provider == "openai":
        from langchain_openai import ChatOpenAI

        kwargs: dict = {"model": settings.llm_model, "api_key": api_key, "temperature": 0}
        if settings.llm_base_url:
            kwargs["base_url"] = settings.llm_base_url
        return ChatOpenAI(**kwargs)

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ConfigurationError(
                "Provider 'anthropic' requires the langchain-anthropic package. "
                "Install it with: pip install langchain-anthropic"
            ) from exc
        return ChatAnthropic(model=settings.llm_model, api_key=api_key, temperature=0)

    if provider == "google":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as exc:  # pragma: no cover - optional dependency
            raise ConfigurationError(
                "Provider 'google' requires the langchain-google-genai package. "
                "Install it with: pip install langchain-google-genai"
            ) from exc
        return ChatGoogleGenerativeAI(
            model=settings.llm_model, google_api_key=api_key, temperature=0
        )

    raise ConfigurationError(f"Unsupported LLM provider: {provider}")  # pragma: no cover
