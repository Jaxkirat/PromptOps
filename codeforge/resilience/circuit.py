"""Per-provider circuit breaker. State lives in this process only."""

from __future__ import annotations

import threading
import time


class CircuitBreaker:
    def __init__(self, threshold: int = 5, cooldown: float = 30.0) -> None:
        self.threshold = threshold
        self.cooldown = cooldown
        self._lock = threading.Lock()
        self._states: dict[str, dict] = {}
        self.opened = 0

    def _entry(self, name: str) -> dict:
        return self._states.setdefault(
            name, {"failures": 0, "state": "closed", "opened_at": 0.0, "probing": False}
        )

    def allow(self, name: str, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            entry = self._entry(name)
            if entry["state"] == "closed":
                return True
            if entry["state"] == "open":
                if now - entry["opened_at"] < self.cooldown:
                    return False
                entry["state"] = "half_open"
                entry["probing"] = True
                return True
            if entry["probing"]:
                return False
            entry["probing"] = True
            return True

    def record_success(self, name: str) -> None:
        with self._lock:
            entry = self._entry(name)
            entry["failures"] = 0
            entry["state"] = "closed"
            entry["probing"] = False

    def record_failure(self, name: str, now: float | None = None) -> None:
        now = time.monotonic() if now is None else now
        with self._lock:
            entry = self._entry(name)
            entry["failures"] += 1
            entry["probing"] = False
            if entry["failures"] >= self.threshold or entry["state"] == "half_open":
                if entry["state"] != "open":
                    self.opened += 1
                entry["state"] = "open"
                entry["opened_at"] = now

    def state_of(self, name: str) -> str:
        with self._lock:
            return self._entry(name)["state"]

    def reset(self) -> None:
        with self._lock:
            self._states.clear()
            self.opened = 0


breakers = CircuitBreaker()
