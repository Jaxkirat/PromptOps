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

    # R1: JWT authentication
    jwt_secret_key: str
    jwt_algorithm: str
    access_token_expire_minutes: int

    # R1: Persistence
    database_url: str

    # R1: Quotas
    max_runs_per_user_per_day: int

    # R1: API server
    api_host: str
    api_port: int
    cors_allowed_origins: tuple[str, ...]

    # R1: Instructor provisioning (trusted server-side configuration)
    initial_instructor_email: str
    initial_instructor_password: str
    initial_instructor_name: str

    # Phase 3: public URL for invitation links and Gradio
    app_base_url: str
    invite_expiry_hours: int

    # R2: sandbox and approvals
    sandbox_backend: str
    sandbox_image: str
    sandbox_timeout_seconds: int
    sandbox_memory_mb: int
    sandbox_cpu_limit: str
    sandbox_pids_limit: int
    sandbox_max_output_bytes: int
    approval_expiry_minutes: int
    checkpoint_path: str

    # R7: read-only SQL agent. The model never receives these caps as authority.
    sql_agent_enabled: bool
    sql_max_rows: int
    sql_default_limit: int
    sql_timeout_seconds: float
    sql_max_result_bytes: int
    sql_max_columns: int
    sql_dialect: str
    sql_sample_database: str
    sql_proposer: str

    # R4: empty means every agent keeps using llm_model.
    llm_model_small: str
    llm_model_large: str

    # R5: provider fallback, retries, circuit breaker, chaos.
    primary_llm_provider: str
    groq_api_key: str
    groq_model: str
    fallback_1_provider: str
    openai_model: str
    fallback_2_provider: str
    fallback_2_api_key: str
    fallback_2_model: str
    llm_max_retries: int
    llm_retry_base_delay: float
    llm_retry_max_delay: float
    llm_circuit_breaker_threshold: int
    llm_circuit_breaker_cooldown: float
    chaos_enabled: bool
    chaos_failure_rate: float

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


def _bool_env(name: str, default: bool) -> bool:
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _float_env(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


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
        jwt_secret_key=os.getenv("JWT_SECRET_KEY", "").strip(),
        jwt_algorithm=os.getenv("JWT_ALGORITHM", "HS256").strip() or "HS256",
        access_token_expire_minutes=_int_env("ACCESS_TOKEN_EXPIRE_MINUTES", 30),
        database_url=os.getenv("DATABASE_URL", "sqlite:///./codeforge.db").strip()
        or "sqlite:///./codeforge.db",
        max_runs_per_user_per_day=_int_env("MAX_RUNS_PER_USER_PER_DAY", 20),
        api_host=os.getenv("API_HOST", "127.0.0.1").strip() or "127.0.0.1",
        api_port=_int_env("API_PORT", 8000),
        cors_allowed_origins=tuple(
            origin.strip()
            for origin in os.getenv("CORS_ALLOWED_ORIGINS", "http://localhost:7860").split(",")
            if origin.strip()
        ),
        initial_instructor_email=os.getenv("INITIAL_INSTRUCTOR_EMAIL", "").strip(),
        initial_instructor_password=os.getenv("INITIAL_INSTRUCTOR_PASSWORD", "").strip(),
        initial_instructor_name=os.getenv("INITIAL_INSTRUCTOR_NAME", "").strip(),
        app_base_url=(
            os.getenv("APP_BASE_URL", "http://127.0.0.1:8000").strip()
            or "http://127.0.0.1:8000"
        ).rstrip("/"),
        invite_expiry_hours=_int_env("INVITE_EXPIRY_HOURS", 72),
        sandbox_backend=os.getenv("CODEFORGE_SANDBOX_BACKEND", "restricted-process").strip()
        or "restricted-process",
        sandbox_image=os.getenv("CODEFORGE_SANDBOX_IMAGE", "codeforge-sandbox:latest").strip()
        or "codeforge-sandbox:latest",
        sandbox_timeout_seconds=_int_env("CODEFORGE_SANDBOX_TIMEOUT_SECONDS", 10),
        sandbox_memory_mb=_int_env("CODEFORGE_SANDBOX_MEMORY_MB", 256),
        sandbox_cpu_limit=os.getenv("CODEFORGE_SANDBOX_CPU_LIMIT", "1").strip() or "1",
        sandbox_pids_limit=_int_env("CODEFORGE_SANDBOX_PIDS_LIMIT", 32),
        sandbox_max_output_bytes=_int_env("CODEFORGE_SANDBOX_MAX_OUTPUT_BYTES", 1048576),
        approval_expiry_minutes=_int_env("APPROVAL_EXPIRY_MINUTES", 60),
        checkpoint_path=os.getenv("CODEFORGE_CHECKPOINT_PATH", "./codeforge_checkpoints.db").strip()
        or "./codeforge_checkpoints.db",
        sql_agent_enabled=_bool_env("CODEFORGE_SQL_AGENT_ENABLED", True),
        sql_max_rows=max(1, _int_env("CODEFORGE_SQL_MAX_ROWS", 500)),
        sql_default_limit=max(1, _int_env("CODEFORGE_SQL_DEFAULT_LIMIT", 100)),
        sql_timeout_seconds=max(0.1, _float_env("CODEFORGE_SQL_TIMEOUT_SECONDS", 2.0)),
        sql_max_result_bytes=max(1000, _int_env("CODEFORGE_SQL_MAX_RESULT_BYTES", 200000)),
        sql_max_columns=max(1, _int_env("CODEFORGE_SQL_MAX_COLUMNS", 16)),
        sql_dialect=os.getenv("CODEFORGE_SQL_DIALECT", "sqlite").strip().lower() or "sqlite",
        sql_sample_database=os.getenv("CODEFORGE_SQL_SAMPLE_DATABASE", "./data/r7_sample.sqlite").strip()
        or "./data/r7_sample.sqlite",
        sql_proposer=os.getenv("CODEFORGE_SQL_PROPOSER", "fixture").strip().lower() or "fixture",
        llm_model_small=os.getenv("LLM_MODEL_SMALL", "").strip(),
        llm_model_large=os.getenv("LLM_MODEL_LARGE", "").strip(),
        primary_llm_provider=os.getenv("PRIMARY_LLM_PROVIDER", "").strip().lower(),
        groq_api_key=os.getenv("GROQ_API_KEY", "").strip(),
        groq_model=os.getenv("GROQ_MODEL", "").strip(),
        fallback_1_provider=os.getenv("FALLBACK_1_PROVIDER", "openai").strip().lower() or "openai",
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        fallback_2_provider=os.getenv("FALLBACK_2_PROVIDER", "").strip().lower(),
        fallback_2_api_key=os.getenv("FALLBACK_2_API_KEY", "").strip(),
        fallback_2_model=os.getenv("FALLBACK_2_MODEL", "").strip(),
        llm_max_retries=max(1, _int_env("LLM_MAX_RETRIES", 3)),
        llm_retry_base_delay=max(0.0, _float_env("LLM_RETRY_BASE_DELAY", 0.5)),
        llm_retry_max_delay=max(0.0, _float_env("LLM_RETRY_MAX_DELAY", 8)),
        llm_circuit_breaker_threshold=max(1, _int_env("LLM_CIRCUIT_BREAKER_THRESHOLD", 5)),
        llm_circuit_breaker_cooldown=max(0.0, _float_env("LLM_CIRCUIT_BREAKER_COOLDOWN", 30)),
        chaos_enabled=_bool_env("CODEFORGE_CHAOS_ENABLED", False)
        and (os.getenv("APP_ENV", "development").strip().lower() != "production"),
        chaos_failure_rate=min(1.0, max(0.0, _float_env("CODEFORGE_CHAOS_FAILURE_RATE", 0.6))),
    )
