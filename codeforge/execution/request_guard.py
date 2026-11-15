"""Request-level refusal for catastrophic intents before any LLM call.

AST policy still gates generated code. This layer catches wipe/delete-home
prompts that previously failed during generation and surfaced as errors.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_WIPE_HOME = re.compile(
    r"""
    (?:
        (?:delete|remove|wipe|erase|destroy)\w*.{0,60}
        (?:every\s*files?|all\s+files?|everything).{0,40}
        (?:home|user)\s*(?:fold(?:er)?|dir(?:ectory)?)
    )
    |
    (?:
        (?:delete|remove|wipe|erase|destroy)\w*.{0,40}
        (?:home|user)\s*(?:fold(?:er)?|dir(?:ectory)?).{0,40}
        (?:every\s*files?|all\s+files?|everything|contents?)
    )
    |
    (?:rm\s+-rf\s+(?:~|\$HOME|/home\b))
    |
    (?:shutil\.rmtree\s*\(\s*(?:Path\.)?home)
    """,
    re.IGNORECASE | re.VERBOSE,
)

_REASON = (
    "Request refused: deleting files under the home directory is blocked by "
    "CodeForge security policy."
)


@dataclass(frozen=True)
class RequestGuardResult:
    denied: bool
    reasons: list[str]


def assess_request(text: str) -> RequestGuardResult:
    """Return deny for clear wipe-home / mass-delete-home intents."""
    cleaned = (text or "").strip()
    if not cleaned:
        return RequestGuardResult(denied=False, reasons=[])
    if _WIPE_HOME.search(cleaned):
        return RequestGuardResult(denied=True, reasons=[_REASON])
    return RequestGuardResult(denied=False, reasons=[])
