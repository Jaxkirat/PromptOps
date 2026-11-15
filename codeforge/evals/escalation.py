"""R3 escalation capability probe.

R3 is not part of this repository. The gate reports escalation cases as pending
instead of treating a missing feature as a pass.
"""

from __future__ import annotations

import importlib.util


def escalation_available() -> bool:
    return importlib.util.find_spec("codeforge.escalation") is not None


def escalation_status() -> dict[str, str | bool]:
    available = escalation_available()
    return {
        "available": available,
        "detail": (
            "R3 escalation is implemented."
            if available
            else "R3 escalation is not implemented. Cases stay pending and are not scored as passes."
        ),
    }
