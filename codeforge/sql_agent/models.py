"""Typed requests and responses for the SQL agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class AccessScope:
    """Server-built scope. The model cannot construct or replace this object."""

    principal_id: str
    role: str
    mode: str
    owner_user_id: str | None
    run_ids: tuple[str, ...]
    ticket_id: str | None
    student_ref: str | None
    allowed_tables: frozenset[str]
    allowed_identifiers: frozenset[str]


@dataclass(frozen=True)
class TicketGrant:
    """One instructor assignment. ``student_id`` never leaves the server."""

    ticket_id: str
    instructor_id: str
    student_id: str
    student_ref: str
    run_ids: tuple[str, ...]
    priority: str
    status: str
    created_at: str
    sla_status: str
    sanitised_request: str
    handoff_summary: str
    attempts: int
    last_failing_test: str


class SqlProposal(BaseModel):
    """What the model is allowed to return. It is not executed as-is."""

    model_config = ConfigDict(extra="ignore")

    sql: str = ""
    parameters: list[Any] = Field(default_factory=list)
    explanation: str = ""


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    sql: str = ""
    category: str = ""
    detail: str = ""
    limit_applied: int | None = None
    clamped: bool = False
    tables: tuple[str, ...] = ()


@dataclass
class QueryResult:
    ok: bool
    columns: list[str] = field(default_factory=list)
    rows: list[list[Any]] = field(default_factory=list)
    truncated: bool = False
    category: str = ""
    executed: bool = False


class SqlAnswer(BaseModel):
    """User-facing result. Failure messages do not claim that rows were read."""

    model_config = ConfigDict(extra="ignore")

    ok: bool
    message: str
    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    truncated: bool = False
    rejection_category: str | None = None
    validated_sql: str | None = None
    limit_applied: int | None = None
    clamped: bool = False
    executed: bool = False
    access_mode: str = ""
    ticket_id: str | None = None


class SqlQueryRequest(BaseModel):
    """Client payload. Identity fields are ignored even if a client sends them."""

    model_config = ConfigDict(extra="ignore")

    question: str = Field(min_length=1, max_length=2000)
    ticket_id: str | None = Field(default=None, max_length=64)
