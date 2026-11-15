"""Core masking engine: ``mask_sensitive_data(text) -> MaskingResult``.

Detected values are replaced with ``[SECRET]``. The result never retains the
original sensitive values — only the sanitized text, a count, and the detected
category names.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from codeforge.privacy.patterns import (
    AADHAAR_PATTERN,
    API_KEY_PATTERNS,
    CARD_CANDIDATE_PATTERN,
    CATEGORY_AADHAAR,
    CATEGORY_API_KEY,
    CATEGORY_CARD,
    CATEGORY_EMAIL,
    CATEGORY_PHONE,
    EMAIL_PATTERN,
    PHONE_PATTERNS,
    luhn_valid,
)

MASK = "[SECRET]"


class MaskingResult(BaseModel):
    """Outcome of masking. Original sensitive values are never stored."""

    sanitized_text: str
    redaction_count: int = Field(ge=0)
    redaction_categories: list[str] = Field(default_factory=list)


def _collect_spans(text: str) -> list[tuple[int, int, str]]:
    """Collect (start, end, category) spans in priority order, skipping overlaps."""
    accepted: list[tuple[int, int, str]] = []

    def overlaps(start: int, end: int) -> bool:
        return any(start < a_end and end > a_start for a_start, a_end, _ in accepted)

    def add_matches(matches: list[tuple[int, int]], category: str) -> None:
        for start, end in matches:
            if not overlaps(start, end):
                accepted.append((start, end, category))

    # 1. API keys (highest priority — unambiguous prefixes)
    for pattern in API_KEY_PATTERNS:
        add_matches([m.span() for m in pattern.finditer(text)], CATEGORY_API_KEY)

    # 2. Emails
    add_matches([m.span() for m in EMAIL_PATTERN.finditer(text)], CATEGORY_EMAIL)

    # 3. Cards (before Aadhaar/phones; Luhn check avoids masking benign numbers)
    card_spans = [
        m.span()
        for m in CARD_CANDIDATE_PATTERN.finditer(text)
        if luhn_valid("".join(ch for ch in m.group() if ch.isdigit()))
    ]
    add_matches(card_spans, CATEGORY_CARD)

    # 4. Aadhaar (12 digits, before 10-digit phone matching)
    add_matches([m.span() for m in AADHAAR_PATTERN.finditer(text)], CATEGORY_AADHAAR)

    # 5. Phone numbers
    for pattern in PHONE_PATTERNS:
        add_matches([m.span() for m in pattern.finditer(text)], CATEGORY_PHONE)

    return sorted(accepted, key=lambda span: span[0])


def mask_sensitive_data(text: str) -> MaskingResult:
    """Mask API keys, emails, phone numbers, Aadhaar and card numbers in ``text``."""
    if not text:
        return MaskingResult(sanitized_text=text or "", redaction_count=0)

    spans = _collect_spans(text)
    if not spans:
        return MaskingResult(sanitized_text=text, redaction_count=0)

    pieces: list[str] = []
    cursor = 0
    categories: set[str] = set()
    for start, end, category in spans:
        pieces.append(text[cursor:start])
        pieces.append(MASK)
        categories.add(category)
        cursor = end
    pieces.append(text[cursor:])

    return MaskingResult(
        sanitized_text="".join(pieces),
        redaction_count=len(spans),
        redaction_categories=sorted(categories),
    )
