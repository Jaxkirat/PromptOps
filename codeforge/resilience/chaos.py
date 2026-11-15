"""Chaos injection is off unless explicitly enabled, and never in production."""

from __future__ import annotations

import random
from collections.abc import Callable

from codeforge.config.settings import get_settings
from codeforge.resilience.errors import TransientProviderError

_forced: Callable[[], bool] | None = None
_rng = random.Random(0)


def set_chaos_rng(rng: random.Random | None) -> None:
    global _rng
    _rng = rng or random.Random(0)


def set_chaos_decider(decider: Callable[[], bool] | None) -> None:
    global _forced
    _forced = decider


def chaos_should_fail() -> bool:
    settings = get_settings()
    if settings.app_env.lower() == "production" or not settings.chaos_enabled:
        return False
    if _forced is not None:
        return _forced()
    return _rng.random() < settings.chaos_failure_rate


def maybe_chaos() -> None:
    if chaos_should_fail():
        raise TransientProviderError("chaos injected a transient provider failure")
