"""Detection patterns for sensitive data, in priority order.

Priority matters for overlap resolution: API keys and emails are unambiguous;
cards are matched before Aadhaar (a 16-digit card contains 12-digit runs);
Aadhaar before phones (a 12-digit run contains 10-digit runs).
"""

from __future__ import annotations

import re

CATEGORY_API_KEY = "api_key"
CATEGORY_EMAIL = "email"
CATEGORY_CARD = "card"
CATEGORY_AADHAAR = "aadhaar"
CATEGORY_PHONE = "phone"

# --- API keys / credentials -------------------------------------------------
# sk- (OpenAI-style), gsk_ (Groq), ghp_/gho_/ghs_/github_pat_ (GitHub),
# AKIA... (AWS access key id), AIza... (Google API key), xox.- (Slack).
API_KEY_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bgsk_[A-Za-z0-9_-]{10,}"),
    re.compile(r"\bgh[posu]_[A-Za-z0-9]{20,}"),
    re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"),
    re.compile(r"\bxox[bpas]-[A-Za-z0-9-]{10,}"),
    # Generic assignment form: api_key=..., apikey: '...', secret_key = "..."
    re.compile(
        r"(?i)\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\b"
        r"\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{12,}['\"]?"
    ),
]

# --- Emails -------------------------------------------------------------------
EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# --- Payment cards ------------------------------------------------------------
# 13-19 digits, optionally separated by spaces/hyphens; Luhn-validated in code.
CARD_CANDIDATE_PATTERN = re.compile(r"(?<![\d-])(?:\d[ -]?){12,18}\d(?![\d-])")

# --- Aadhaar ------------------------------------------------------------------
# 12 digits (Aadhaar never starts with 0 or 1), plain, spaced or hyphenated.
# The lookbehind excludes '+' so "+919876543210" is treated as a phone number.
AADHAAR_PATTERN = re.compile(r"(?<![\d+-])[2-9]\d{3}([ -]?)\d{4}\1\d{4}(?![\d-])")

# --- Phone numbers ------------------------------------------------------------
PHONE_PATTERNS: list[re.Pattern[str]] = [
    # +91 Indian formats: +91 9876543210, +91-98765-43210, +919876543210
    re.compile(r"(?<!\d)\+91[ -]?[6-9]\d{4}[ -]?\d{5}(?!\d)"),
    # Other international: +44 20 7946 0958, +1-202-555-0143 ...
    re.compile(r"(?<![\d-])\+\d{1,3}(?:[ -]?\d{2,5}){2,4}(?![\d-])"),
    # Bare Indian mobile: 10 digits starting 6-9
    re.compile(r"(?<![\d-])[6-9]\d{9}(?![\d-])"),
]


def luhn_valid(digits: str) -> bool:
    """Return True if ``digits`` passes the Luhn checksum."""
    if not digits.isdigit() or len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    for index, char in enumerate(reversed(digits)):
        value = int(char)
        if index % 2 == 1:
            value *= 2
            if value > 9:
                value -= 9
        total += value
    return total % 10 == 0
