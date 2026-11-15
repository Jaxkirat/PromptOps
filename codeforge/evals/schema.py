"""Versioned golden-dataset schema."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class GoldenCase(BaseModel):
    id: str = Field(min_length=3)
    category: str = Field(min_length=2)
    severity: Literal["hard", "soft"]
    description: str = Field(min_length=8)
    input: dict[str, Any]
    expected: dict[str, Any]
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True
    mandatory: bool = True
    scoring: Literal["scored", "pending"] = "scored"
    pending_reason: str = ""

    @field_validator("expected")
    @classmethod
    def expected_present(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not value:
            raise ValueError("expected outcomes must be explicit")
        return value

    @model_validator(mode="after")
    def pending_rules(self) -> "GoldenCase":
        if self.severity == "hard" and self.scoring == "pending":
            raise ValueError(f"{self.id}: hard cases cannot be pending")
        if self.scoring == "pending" and not self.pending_reason:
            raise ValueError(f"{self.id}: pending cases need a pending_reason")
        return self


class GoldenDataset(BaseModel):
    version: str
    description: str
    cases: list[GoldenCase]

    @model_validator(mode="after")
    def unique_and_complete(self) -> "GoldenDataset":
        ids = [case.id for case in self.cases]
        duplicates = sorted({case_id for case_id in ids if ids.count(case_id) > 1})
        if duplicates:
            raise ValueError(f"duplicate case ids: {', '.join(duplicates)}")
        hard = [case for case in self.cases if case.severity == "hard" and case.scoring == "scored"]
        soft = [case for case in self.cases if case.severity == "soft" and case.scoring == "scored"]
        if not hard:
            raise ValueError("dataset has zero scored hard cases")
        if not soft:
            raise ValueError("dataset has zero scored soft cases")
        disabled_mandatory = [case.id for case in self.cases if case.mandatory and not case.enabled]
        if disabled_mandatory:
            raise ValueError(
                "mandatory cases are disabled and would shrink the gate: "
                + ", ".join(disabled_mandatory)
            )
        return self
