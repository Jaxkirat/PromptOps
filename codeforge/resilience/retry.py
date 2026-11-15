"""Exponential backoff with full jitter. Tests can replace the sleeper."""

from __future__ import annotations

import random
import time
from collections.abc import Callable

from codeforge.resilience.errors import FatalProviderError, TransientProviderError, classify_exception

_sleep: Callable[[float], None] = time.sleep
_rng = random.Random()


def set_retry_sleeper(sleeper: Callable[[float], None] | None) -> None:
    global _sleep
    _sleep = sleeper or time.sleep


def set_retry_rng(rng: random.Random | None) -> None:
    global _rng
    _rng = rng or random.Random()


def retry_call(operation: Callable[[], object], *, attempts: int, base_delay: float, max_delay: float):
    """Retry transient failures. Fatal failures propagate immediately."""
    last: Exception | None = None
    used = 0
    for attempt in range(attempts):
        used = attempt + 1
        try:
            return operation(), used
        except FatalProviderError:
            raise
        except Exception as exc:
            kind = classify_exception(exc)
            if kind != "transient":
                raise FatalProviderError(str(exc)) from exc
            last = exc
            if attempt + 1 >= attempts:
                break
            retry_after = getattr(exc, "retry_after", None)
            delay = retry_after if isinstance(retry_after, (int, float)) else min(max_delay, base_delay * (2**attempt))
            _sleep(_rng.random() * delay if delay else 0)
    raise TransientProviderError(str(last) if last else "transient provider failure")
