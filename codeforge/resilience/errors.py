"""Classify provider failures. Authentication and bad requests are not retried."""

from __future__ import annotations


class TransientProviderError(Exception):
    """Retryable provider failure: rate limit, 5xx, timeout, or connection loss."""

    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class FatalProviderError(Exception):
    """Do not retry: authentication, invalid request, or unsupported model."""


class AllProvidersFailed(Exception):
    """Every configured provider failed or was skipped by its circuit breaker."""


def classify_exception(exc: Exception) -> str:
    if isinstance(exc, TransientProviderError):
        return "transient"
    if isinstance(exc, FatalProviderError):
        return "fatal"
    status = getattr(exc, "status_code", None)
    text = str(exc).lower()
    if status in {401, 403} or any(token in text for token in ("invalid api key", "authentication", "unauthorized", "invalid request", "model not found")):
        return "fatal"
    if status == 429 or (isinstance(status, int) and status >= 500):
        return "transient"
    if any(token in text for token in ("429", "rate limit", "timeout", "timed out", "connection", "502", "503", "504")):
        return "transient"
    return "fatal"
