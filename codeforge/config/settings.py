"""Application settings loaded from environment variables (.env supported).

All configuration access goes through :func:`get_settings` so that the rest of
the codebase never reads ``os.environ`` directly.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of the application configuration."""

    # LLM provider configuration
    llm_provider: str
    llm_model: str
    llm_api_key: str
    llm_base_url: str

    # Optional provider-specific keys
    openai_api_key: str
    anthropic_api_key: str
    google_api_key: str

    # Application
    app_env: str
    log_level: str

    # Execution
    execution_timeout_seconds: int
    max_test_output_length: int

    def resolve_api_key(self) -> str:
        """Return the API key for the configured provider.

        The generic ``LLM_API_KEY`` takes precedence; otherwise the
        provider-specific variable is used.
        """
        if self.llm_api_key:
            return self.llm_api_key
        provider_keys = {
            "openai": self.openai_api_key,
            "anthropic": self.anthropic_api_key,
            "google": self.google_api_key,
        }
        return provider_keys.get(self.llm_provider.lower(), "")


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load settings from the environment (reading .env once if present)."""
    load_dotenv()
    return Settings(
        llm_provider=os.getenv("LLM_PROVIDER", "openai").strip() or "openai",
        llm_model=os.getenv("LLM_MODEL", "gpt-4.1-mini").strip() or "gpt-4.1-mini",
        llm_api_key=os.getenv("LLM_API_KEY", "").strip(),
        llm_base_url=os.getenv("LLM_BASE_URL", "").strip(),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", "").strip(),
        google_api_key=os.getenv("GOOGLE_API_KEY", "").strip(),
        app_env=os.getenv("APP_ENV", "development").strip() or "development",
        log_level=os.getenv("LOG_LEVEL", "INFO").strip() or "INFO",
        execution_timeout_seconds=_int_env("EXECUTION_TIMEOUT_SECONDS", 15),
        max_test_output_length=_int_env("MAX_TEST_OUTPUT_LENGTH", 10000),
    )
