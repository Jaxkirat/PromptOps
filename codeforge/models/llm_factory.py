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


def _openai_model(model: str, api_key: str, base_url: str = "") -> BaseChatModel:
    from langchain_openai import ChatOpenAI

    kwargs: dict = {"model": model, "api_key": api_key, "temperature": 0}
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def _provider_chain(settings: Settings) -> list[tuple[str, str, BaseChatModel]]:
    """Primary model first, then configured fallbacks that have their own credentials."""
    validate_llm_config(settings)
    primary_key = settings.resolve_api_key()
    primary_model = settings.groq_model or settings.llm_model
    base_url = settings.llm_base_url
    if settings.primary_llm_provider == "groq" and settings.groq_api_key:
        primary_key = settings.groq_api_key
        base_url = base_url or "https://api.groq.com/openai/v1"
    primary_name = "groq" if "groq" in base_url or settings.primary_llm_provider == "groq" else settings.llm_provider.lower()
    if primary_name == "openai" and "groq" not in base_url:
        chain = [("openai", settings.llm_model, _openai_model(settings.llm_model, primary_key, base_url))]
    elif primary_name in {"anthropic", "google"} and settings.primary_llm_provider not in {"", "groq"}:
        chain = [(primary_name, settings.llm_model, _build_named(settings, primary_name, settings.llm_model, primary_key, base_url))]
    else:
        chain = [(primary_name, primary_model, _openai_model(primary_model, primary_key, base_url))]
    if (
        settings.fallback_1_provider == "openai"
        and settings.openai_api_key
        and not any(name == "openai" and not settings.llm_base_url for name, _model, _client in chain)
    ):
        chain.append(("openai", settings.openai_model, _openai_model(settings.openai_model, settings.openai_api_key)))
    if settings.fallback_2_provider and settings.fallback_2_api_key and settings.fallback_2_model:
        chain.append(
            (
                settings.fallback_2_provider,
                settings.fallback_2_model,
                _openai_model(settings.fallback_2_model, settings.fallback_2_api_key),
            )
        )
    logger.info("provider_chain=%s", [name for name, _model, _client in chain])
    return chain


def _build_named(settings: Settings, provider: str, model: str, api_key: str, base_url: str) -> BaseChatModel:
    del settings
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        return ChatAnthropic(model=model, api_key=api_key, temperature=0)
    if provider == "google":
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=model, google_api_key=api_key, temperature=0)
    return _openai_model(model, api_key, base_url)


def create_llm(settings: Settings | None = None):
    """Create the configured model, with retries and fallbacks when more than one provider is set.

    A single configured provider is returned directly so existing callers keep the same client.
    """
    settings = settings or get_settings()
    chain = _provider_chain(settings)
    if len(chain) == 1 and not settings.chaos_enabled:
        return chain[0][2]
    from codeforge.resilience.fallback import ResilientChatModel

    return ResilientChatModel(chain, settings)
