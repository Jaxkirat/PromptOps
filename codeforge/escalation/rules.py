"""Escalation rules. This module does not call a model."""

from __future__ import annotations

from pydantic import BaseModel

from codeforge.escalation.triage import TriageResult

SLA_HOURS = 4
PRIORITY = "P1"


class EscalationDecision(BaseModel):
    should_escalate: bool
    trigger_reason: str = ""
    priority: str = PRIORITY
    sla_hours: int = SLA_HOURS


def should_escalate(
    triage_result: TriageResult,
    consecutive_negative: int,
    repair_failure_count: int,
    policy_denial_count: int,
) -> EscalationDecision:
    """Return whether this turn must open or reuse a P1 ticket."""
    if triage_result.wants_human:
        reason = "explicit_human"
    elif triage_result.sentiment == "angry":
        reason = "angry_sentiment"
    elif consecutive_negative >= 2:
        reason = "two_negative"
    elif repair_failure_count >= 2:
        reason = "repair_failures"
    elif policy_denial_count >= 2:
        reason = "policy_denials"
    else:
        return EscalationDecision(should_escalate=False)
    return EscalationDecision(should_escalate=True, trigger_reason=reason)


def next_negative_count(previous: int, sentiment: str) -> int:
    """Angry turns escalate on their own. Neutral and positive reset the counter."""
    if sentiment == "negative":
        return previous + 1
    if sentiment in {"neutral", "positive"}:
        return 0
    return previous
