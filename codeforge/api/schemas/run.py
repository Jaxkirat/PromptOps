"""Run API schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from codeforge.services.run_service import RunRecord


class RunSubmitRequest(BaseModel):
    """Run submission payload.

    ``extra="forbid"``: identity- or privilege-related fields such as
    ``user_id``, ``role``, ``owner_id``, ``is_instructor`` or
    ``quota_override`` are hard-rejected with 422. Ownership is always derived
    from the authenticated token, never from the request body.
    """

    model_config = ConfigDict(extra="forbid")

    request: str = Field(min_length=1, max_length=8000, description="Natural-language coding request.")


class RunListResponse(BaseModel):
    runs: list[RunRecord]
    total: int


__all__ = ["RunSubmitRequest", "RunListResponse", "RunRecord"]
