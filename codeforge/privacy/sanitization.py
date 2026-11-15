"""Sanitization helpers applied before persistence and logging.

Defence in depth: even though the LLM only ever sees sanitized input, any
generated content is masked again before being stored, in case a model echoes
something sensitive. The same service is reusable by future R3 ticket
generation.
"""

from __future__ import annotations

from codeforge.privacy.masker import mask_sensitive_data


def sanitize_for_storage(text: str | None) -> str | None:
    """Mask sensitive data in ``text`` before it is persisted or logged."""
    if text is None:
        return None
    return mask_sensitive_data(text).sanitized_text
