"""Pass/fail arithmetic for the release gate."""

from __future__ import annotations

from dataclasses import dataclass, field

from codeforge.evals.thresholds import HARD_THRESHOLD_PERCENT, SOFT_THRESHOLD_PERCENT, meets_threshold


@dataclass
class GateDecision:
    hard_passed: int
    hard_total: int
    soft_passed: int
    soft_total: int
    hard_ok: bool
    soft_ok: bool
    status: str
    reasons: list[str] = field(default_factory=list)
    pending: int = 0

    @property
    def green(self) -> bool:
        return self.status == "GREEN"


def decide_gate(
    hard_passed: int,
    hard_total: int,
    soft_passed: int,
    soft_total: int,
    *,
    infrastructure_ok: bool = True,
    infrastructure_errors: list[str] | None = None,
    pending: int = 0,
) -> GateDecision:
    reasons: list[str] = []
    if hard_total <= 0:
        reasons.append("Zero hard cases is invalid.")
    if soft_total <= 0:
        reasons.append("Zero soft cases is invalid.")
    if not infrastructure_ok:
        reasons.extend(infrastructure_errors or ["Evaluation infrastructure is missing."])

    hard_ok = hard_total > 0 and meets_threshold(hard_passed, hard_total, HARD_THRESHOLD_PERCENT)
    soft_ok = soft_total > 0 and meets_threshold(soft_passed, soft_total, SOFT_THRESHOLD_PERCENT)
    if hard_total > 0 and not hard_ok:
        reasons.append("One or more hard cases failed.")
    if soft_total > 0 and not soft_ok:
        reasons.append(
            f"Soft score is below {SOFT_THRESHOLD_PERCENT}% "
            f"({soft_passed}/{soft_total})."
        )
    green = hard_ok and soft_ok and infrastructure_ok and not reasons
    return GateDecision(
        hard_passed=hard_passed,
        hard_total=hard_total,
        soft_passed=soft_passed,
        soft_total=soft_total,
        hard_ok=hard_ok,
        soft_ok=soft_ok,
        status="GREEN" if green else "RED",
        reasons=reasons,
        pending=pending,
    )
