"""Try the primary model, then configured fallbacks. One structured-output call at a time."""

from __future__ import annotations

import logging

from codeforge.config.settings import Settings, get_settings
from codeforge.resilience.chaos import maybe_chaos
from codeforge.resilience.circuit import breakers
from codeforge.resilience.errors import AllProvidersFailed, FatalProviderError, TransientProviderError
from codeforge.resilience.retry import retry_call

logger = logging.getLogger(__name__)
_metadata: dict = {}


def last_provider_metadata() -> dict:
    return dict(_metadata)


class ResilientChatModel:
    """Small wrapper. Agents only need invoke and with_structured_output."""

    def __init__(self, providers: list[tuple[str, str, object]], settings: Settings) -> None:
        self.providers = providers
        self.settings = settings

    def with_structured_output(self, schema, **kwargs):
        bound = [
            (name, model_name, model.with_structured_output(schema, **kwargs))
            for name, model_name, model in self.providers
        ]
        return _Bound(bound, self.settings)

    def invoke(self, messages, **kwargs):
        return _call(self.providers, self.settings, lambda model: model.invoke(messages, **kwargs))


class _Bound:
    def __init__(self, providers, settings: Settings) -> None:
        self.providers = providers
        self.settings = settings

    def invoke(self, messages, **kwargs):
        return _call(self.providers, self.settings, lambda model: model.invoke(messages, **kwargs))


def _call(providers, settings: Settings, operation) -> object:
    global _metadata
    attempts = []
    for name, model_name, model in providers:
        if not breakers.allow(name):
            attempts.append({"provider": name, "model": model_name, "result": "circuit_open"})
            continue
        try:
            def attempt(model=model):
                maybe_chaos()
                return operation(model)

            result, used = retry_call(
                attempt,
                attempts=settings.llm_max_retries,
                base_delay=settings.llm_retry_base_delay,
                max_delay=settings.llm_retry_max_delay,
            )
            breakers.record_success(name)
            attempts.append({"provider": name, "model": model_name, "result": "success", "tries": used})
            _metadata = {
                "provider": name,
                "model": model_name,
                "fallback_used": name != providers[0][0],
                "provider_attempts": attempts,
                "generation_source": "llm",
            }
            logger.info("llm_success provider=%s model=%s fallback=%s", name, model_name, _metadata["fallback_used"])
            return result
        except FatalProviderError as exc:
            attempts.append({"provider": name, "model": model_name, "result": "fatal"})
            logger.info("llm_fatal provider=%s", name)
            continue
        except TransientProviderError:
            breakers.record_failure(name)
            attempts.append({"provider": name, "model": model_name, "result": "transient_exhausted"})
            logger.info("llm_transient_exhausted provider=%s", name)
            continue
    _metadata = {"provider": "", "model": "", "fallback_used": False, "provider_attempts": attempts, "generation_source": "unavailable"}
    raise AllProvidersFailed("Code generation is temporarily unavailable.")
