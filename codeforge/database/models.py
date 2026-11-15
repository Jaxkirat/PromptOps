"""ORM models: users, runs, quota usage and revoked tokens.

Raw user requests are NEVER stored — only the sanitised request text
(``Run.sanitised_request``) after PII/secret masking.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from codeforge.database.database import Base

ROLE_STUDENT = "student"
ROLE_INSTRUCTOR = "instructor"
VALID_ROLES = (ROLE_STUDENT, ROLE_INSTRUCTOR)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return uuid.uuid4().hex


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default=ROLE_STUDENT)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )

    runs: Mapped[list["Run"]] = relationship(back_populates="owner")
    conversations: Mapped[list["Conversation"]] = relationship(back_populates="owner")


class Conversation(Base):
    """A user's chat. The title is taken from sanitised text, never a raw prompt."""

    __tablename__ = "conversations"
    __table_args__ = (Index("ix_conversations_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False, default="")
    escalation_state_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    owner: Mapped[User] = relationship(back_populates="conversations")
    messages: Mapped[list["Message"]] = relationship(back_populates="conversation")
    runs: Mapped[list["Run"]] = relationship(back_populates="conversation")


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (Index("ix_runs_user_created", "user_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id"), index=True, nullable=False
    )
    conversation_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("conversations.id"), nullable=True
    )
    sanitised_request: Mapped[str] = mapped_column(Text, nullable=False)
    task_type: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    generated_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    generated_tests: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_results: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON summary
    artifacts_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    execution_time: Mapped[float | None] = mapped_column(Float, nullable=True)
    redaction_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    llm_usage_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    owner: Mapped[User] = relationship(back_populates="runs")
    conversation: Mapped[Conversation | None] = relationship(back_populates="runs")


class Message(Base):
    """Sanitised chat line. ``role`` is user or assistant, not an account role."""

    __tablename__ = "messages"
    __table_args__ = (Index("ix_messages_conversation_created", "conversation_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    conversation_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("conversations.id"), nullable=False
    )
    run_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("runs.id"), nullable=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Ticket(Base):
    """One current instructor per handoff. Reassignment updates ``instructor_id``."""

    __tablename__ = "tickets"
    __table_args__ = (
        Index("ix_tickets_student_status", "student_id", "status"),
        Index("ix_tickets_instructor_status", "instructor_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    student_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    instructor_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("runs.id"), nullable=True)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="normal")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="open")
    trigger_reason: Mapped[str] = mapped_column(Text, nullable=False, default="")
    handoff_note: Mapped[str] = mapped_column(Text, nullable=False, default="")
    last_failing_test: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    sla_due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    replies: Mapped[list["TicketMessage"]] = relationship(back_populates="ticket")


class TicketMessage(Base):
    """In-app reply. ``email_status`` records delivery and never replaces the message."""

    __tablename__ = "ticket_messages"
    __table_args__ = (Index("ix_ticket_messages_ticket_created", "ticket_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    ticket_id: Mapped[str] = mapped_column(String(32), ForeignKey("tickets.id"), nullable=False)
    sender_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False, default="")
    email_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

    ticket: Mapped[Ticket] = relationship(back_populates="replies")


class AssignmentState(Base):
    """Single-row round-robin cursor. It survives process restarts."""

    __tablename__ = "assignment_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cursor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class QuotaUsage(Base):
    __tablename__ = "quota_usage"
    __table_args__ = (UniqueConstraint("user_id", "usage_date", name="uq_quota_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("users.id"), index=True, nullable=False
    )
    usage_date: Mapped[date] = mapped_column(Date, nullable=False)  # UTC date
    reserved_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    quota_limit: Mapped[int] = mapped_column(Integer, nullable=False)


class InstructorInvitation(Base):
    """Hashed, single-use, expiring instructor invitation.

    The plaintext token is never stored — only ``token_hash``.
    """

    __tablename__ = "instructor_invitations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    created_by: Mapped[str] = mapped_column(String(50), nullable=False, default="cli")


class RevokedToken(Base):
    """JWT jti values revoked by logout; checked on every authentication."""

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(32), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ExecutionRecord(Base):
    """One policy+sandbox outcome per user/code/tests hash."""

    __tablename__ = "execution_records"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("runs.id"), nullable=True)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_decision: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_reasons_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    sandbox_backend: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ApprovalRequest(Base):
    """Human approval pause. Decisions are atomic on status='pending'."""

    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, nullable=False)
    run_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("runs.id"), nullable=True)
    thread_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending", index=True)
    reasons_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    operations_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    code_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tests_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approver_id: Mapped[str | None] = mapped_column(String(32), ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resume_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class SqlQueryAudit(Base):
    """Append-only record of a SQL-agent attempt.

    The agent cannot update or delete these rows: its allowlist does not include
    this table, and it never receives the application write session.
    """

    __tablename__ = "sql_query_audits"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    access_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    ticket_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    sanitised_question: Mapped[str] = mapped_column(Text, nullable=False, default="")
    validated_sql: Mapped[str] = mapped_column(Text, nullable=False, default="")
    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rejection_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class RunFeedback(Base):
    """One thumbs rating per user and run. Explanations are stored masked."""

    __tablename__ = "run_feedback"
    __table_args__ = (UniqueConstraint("user_id", "run_id", name="uq_feedback_user_run"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_id)
    user_id: Mapped[str] = mapped_column(String(32), ForeignKey("users.id"), index=True, nullable=False)
    run_id: Mapped[str] = mapped_column(String(32), ForeignKey("runs.id"), index=True, nullable=False)
    vote: Mapped[str] = mapped_column(String(8), nullable=False)
    explanation: Mapped[str] = mapped_column(Text, nullable=False, default="")
    sanitised_request: Mapped[str] = mapped_column(Text, nullable=False, default="")
    result_ref: Mapped[str] = mapped_column(Text, nullable=False, default="")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="recorded")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
