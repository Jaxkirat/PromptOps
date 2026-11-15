"""Keep recent turns and the constraints from older turns."""

from __future__ import annotations

KEEP_RECENT = 5
COMPACT_AFTER = 8
_IMPORTANT = ("must", "constraint", "edge", "signature", "return", "o(n)", "do not")


def compact_messages(messages: list[dict], *, keep_recent: int = KEEP_RECENT, after: int = COMPACT_AFTER) -> tuple[list[dict], bool]:
    if len(messages) <= after:
        return list(messages), False
    older = messages[:-keep_recent]
    recent = messages[-keep_recent:]
    kept = [
        message
        for message in older
        if any(term in str(message.get("content", "")).lower() for term in _IMPORTANT)
    ]
    summary = " ".join(str(message.get("content", ""))[:160] for message in kept)
    compacted = [{"role": "system", "content": f"Preserved constraints: {summary}"}]
    compacted.extend(recent)
    return compacted, True
