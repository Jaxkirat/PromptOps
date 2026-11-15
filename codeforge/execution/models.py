"""R2 structured results for policy decisions and sandboxed execution."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

POLICY_VERSION = "r2.1"

PolicyDecision = Literal["allow", "needs_approval", "deny"]


class PolicyResult(BaseModel):
    """Deterministic AST policy decision. Never produced by an LLM."""

    decision: PolicyDecision
    reasons: list[str] = Field(default_factory=list)
    detected_operations: list[str] = Field(default_factory=list)
    detected_imports: list[str] = Field(default_factory=list)
    policy_version: str = POLICY_VERSION
    requires_approval: bool = False
