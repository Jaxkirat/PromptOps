"""Isolated subject for the feedback flywheel demonstration.

This is not the production router. The buggy predicate is what the candidate
case fails against. The fixed predicate is applied only inside the demo.
"""

from __future__ import annotations


def classify_label(text: str) -> str:
    """Buggy: the word "query" forces SQL even for a Python function request."""
    lowered = text.lower()
    if "query" in lowered:
        return "sql"
    if "python" in lowered or "function" in lowered:
        return "python"
    return "other"


def classify_label_fixed(text: str) -> str:
    """Python function requests stay Python even if they mention a query string."""
    lowered = text.lower()
    if "python" in lowered and "function" in lowered:
        return "python"
    if "sql" in lowered:
        return "sql"
    if "query" in lowered:
        return "sql"
    if "python" in lowered or "function" in lowered:
        return "python"
    return "other"
