"""Conservative cache. Embeddings are not configured, so matching is token overlap plus guard terms."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass

SIMILARITY_THRESHOLD = 0.92
TTL_SECONDS = 24 * 60 * 60
MAX_ENTRIES = 128

_CONTEXT = re.compile(
    r"\b(my code|previous code|this error|the error above|above|continue|my run|this bug)\b",
    re.IGNORECASE,
)
_GUARDS = (
    frozenset({"ascending", "descending"}),
    frozenset({"list", "set"}),
    frozenset({"recursive", "iterative"}),
    frozenset({"in-place", "inplace", "new-list"}),
    frozenset({"case-sensitive", "case-insensitive"}),
    frozenset({"python", "javascript"}),
    frozenset({"duplicates", "unique"}),
    frozenset({"o(n)", "unrestricted"}),
)


def is_cacheable(text: str, *, redactions: int = 0) -> bool:
    if redactions or not text or not text.strip():
        return False
    if _CONTEXT.search(text):
        return False
    lowered = text.lower()
    if "debug" in lowered or "fix the" in lowered:
        return False
    return True


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9()]+", text.lower().replace(" ", ""))) | set(re.findall(r"[a-z0-9]+", text.lower()))


def _guard_signature(text: str) -> tuple[str, ...]:
    lowered = text.lower().replace(" ", "-")
    found = []
    for group in _GUARDS:
        hits = sorted(term for term in group if term in lowered or term.replace("-", " ") in text.lower())
        if hits:
            found.append(hits[0])
    return tuple(found)


def similarity(left: str, right: str) -> float:
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


@dataclass
class CacheEntry:
    text: str
    language: str
    task_type: str
    artifact: str
    stored_at: float


class SemanticCache:
    def __init__(self, threshold: float = SIMILARITY_THRESHOLD, ttl_seconds: int = TTL_SECONDS, max_entries: int = MAX_ENTRIES) -> None:
        self.threshold = threshold
        self.ttl_seconds = ttl_seconds
        self.max_entries = max_entries
        self._entries: list[CacheEntry] = []

    def get(self, text: str, *, language: str, task_type: str, now: float | None = None) -> str | None:
        if not is_cacheable(text):
            return None
        now = time.time() if now is None else now
        self._expire(now)
        signature = _guard_signature(text)
        for entry in self._entries:
            if entry.language != language or entry.task_type != task_type:
                continue
            if _guard_signature(entry.text) != signature:
                continue
            if similarity(entry.text, text) >= self.threshold:
                return entry.artifact
        return None

    def put(self, text: str, artifact: str, *, language: str, task_type: str, now: float | None = None) -> None:
        if not is_cacheable(text):
            return
        now = time.time() if now is None else now
        self._entries.append(CacheEntry(text, language, task_type, artifact, now))
        self._expire(now)
        if len(self._entries) > self.max_entries:
            self._entries = self._entries[-self.max_entries :]

    def _expire(self, now: float) -> None:
        self._entries = [entry for entry in self._entries if now - entry.stored_at <= self.ttl_seconds]
