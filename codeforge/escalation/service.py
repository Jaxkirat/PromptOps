"""Ticket creation, round-robin assignment, replies and notification status."""

from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from codeforge.auth.identity import current_principal
from codeforge.database.database import session_scope
from codeforge.database.models import (
    ROLE_INSTRUCTOR,
    AssignmentState,
    Conversation,
    Run,
    Ticket,
    TicketMessage,
    User,
)
from codeforge.escalation.rules import PRIORITY, SLA_HOURS, EscalationDecision
from codeforge.exceptions import SqlTicketNotFoundError
from codeforge.privacy.masker import mask_sensitive_data

logger = logging.getLogger(__name__)
_assign_lock = threading.Lock()
_email_sender: Callable[[str, str, str], str] | None = None
OPEN_STATUSES = ("open", "in_progress", "awaiting_assignment")
VISIBLE_STATUSES = ("open", "in_progress")


def set_email_sender(sender: Callable[[str, str, str], str] | None) -> None:
    global _email_sender
    _email_sender = sender


def _utcnow() -> datetime:
    """Naive UTC. SQLite returns naive datetimes, so comparisons stay naive."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _notify(email: str, subject: str, body: str) -> str:
    sender = _email_sender
    if sender is None:
        return "unconfigured"
    try:
        return sender(email, subject, body)
    except Exception:
        logger.info("ticket_email_failed")
        return "failed"


def assign_next_instructor(session) -> str | None:
    """Persist a round-robin cursor and skip inactive instructors."""
    instructors = (
        session.query(User)
        .filter(User.role == ROLE_INSTRUCTOR, User.is_active.is_(True))
        .order_by(User.id)
        .all()
    )
    if not instructors:
        return None
    with _assign_lock:
        state = session.get(AssignmentState, 1)
        if state is None:
            state = AssignmentState(id=1, cursor=0)
            session.add(state)
            session.flush()
        chosen = instructors[state.cursor % len(instructors)]
        state.cursor = state.cursor + 1
        session.flush()
        return chosen.id


def _public_ticket(ticket: Ticket, run: Run | None) -> dict[str, Any]:
    now = _utcnow()
    due = ticket.sla_due_at
    if due is not None and due.tzinfo is not None:
        due = due.astimezone(timezone.utc).replace(tzinfo=None)
    if ticket.first_response_at is not None:
        sla_status = "responded"
    elif due is not None and now > due:
        sla_status = "overdue"
    else:
        sla_status = "within_sla"
    return {
        "id": ticket.id,
        "priority": ticket.priority,
        "status": ticket.status,
        "trigger_reason": ticket.trigger_reason,
        "handoff_note": ticket.handoff_note,
        "last_failing_test": ticket.last_failing_test,
        "created_at": ticket.created_at.isoformat() if ticket.created_at else "",
        "sla_due_at": due.isoformat() if due else "",
        "sla_status": sla_status,
        "first_response_at": ticket.first_response_at.isoformat() if ticket.first_response_at else None,
        "run_id": ticket.run_id,
        "language": run.language if run else None,
        "sanitised_request": run.sanitised_request if run else "",
        "generated_code": run.generated_code if run else "",
        "generated_tests": run.generated_tests if run else "",
    }


def build_handoff(run: Run | None, decision: EscalationDecision) -> tuple[str, str]:
    request = mask_sensitive_data(run.sanitised_request if run else "").sanitized_text
    code = mask_sensitive_data((run.generated_code if run else "") or "").sanitized_text
    tests = mask_sensitive_data((run.generated_tests if run else "") or "").sanitized_text
    note = (
        f"Reason: {decision.trigger_reason}. Priority {decision.priority}. "
        f"Request: {request[:500]}. "
        f"Language: {(run.language if run else '') or 'unknown'}. "
        f"Latest code is stored on the run. "
        f"Suggested next step: review the failing test and the latest code."
    )
    failing = ""
    if run and run.test_results:
        failing = "see test_results"
    return mask_sensitive_data(note).sanitized_text, failing or (run.status if run else "")


def open_ticket(conversation_id: str, run_id: str | None, decision: EscalationDecision) -> dict[str, Any]:
    """Create or reuse one unresolved ticket for this conversation."""
    principal = current_principal()
    with session_scope() as session:
        existing = (
            session.query(Ticket)
            .join(Run, Ticket.run_id == Run.id)
            .filter(Run.conversation_id == conversation_id, Ticket.status.in_(OPEN_STATUSES))
            .first()
        )
        if existing is None and run_id:
            existing = (
                session.query(Ticket)
                .filter(Ticket.run_id == run_id, Ticket.status.in_(OPEN_STATUSES))
                .first()
            )
        run = session.get(Run, run_id) if run_id else None
        if existing is not None:
            return _public_ticket(existing, run or session.get(Run, existing.run_id))
        instructor_id = assign_next_instructor(session)
        note, failing = build_handoff(run, decision)
        now = _utcnow()
        ticket = Ticket(
            student_id=principal.user_id,
            instructor_id=instructor_id,
            run_id=run_id,
            priority=PRIORITY,
            status="open" if instructor_id else "awaiting_assignment",
            trigger_reason=decision.trigger_reason,
            handoff_note=note,
            last_failing_test=failing,
            sla_due_at=now + timedelta(hours=SLA_HOURS),
        )
        session.add(ticket)
        session.flush()
        return _public_ticket(ticket, run)


def list_my_tickets() -> list[dict[str, Any]]:
    principal = current_principal()
    with session_scope() as session:
        query = session.query(Ticket)
        if principal.role == ROLE_INSTRUCTOR:
            query = query.filter(Ticket.instructor_id == principal.user_id, Ticket.status.in_(VISIBLE_STATUSES))
        else:
            query = query.filter(Ticket.student_id == principal.user_id)
        rows = []
        for ticket in query.order_by(Ticket.created_at.desc()).all():
            rows.append(_public_ticket(ticket, session.get(Run, ticket.run_id) if ticket.run_id else None))
        return rows


def get_ticket(ticket_id: str) -> dict[str, Any]:
    principal = current_principal()
    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None or not _can_see(ticket, principal.user_id, principal.role):
            raise SqlTicketNotFoundError()
        run = session.get(Run, ticket.run_id) if ticket.run_id else None
        payload = _public_ticket(ticket, run)
        payload["replies"] = [
            {
                "id": reply.id,
                "role": "instructor" if reply.sender_id == ticket.instructor_id else "student",
                "message": reply.message,
                "created_at": reply.created_at.isoformat() if reply.created_at else "",
                "email_status": reply.email_status,
            }
            for reply in ticket.replies
        ]
        return payload


def _can_see(ticket: Ticket, user_id: str, role: str) -> bool:
    if ticket.student_id == user_id:
        return True
    return role == ROLE_INSTRUCTOR and ticket.instructor_id == user_id


def post_reply(ticket_id: str, message: str) -> dict[str, Any]:
    principal = current_principal()
    masked = mask_sensitive_data(message or "").sanitized_text
    if not masked.strip():
        raise ValueError("Reply must not be empty.")
    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        if ticket is None or not _can_see(ticket, principal.user_id, principal.role):
            raise SqlTicketNotFoundError()
        if principal.role == ROLE_INSTRUCTOR and ticket.instructor_id != principal.user_id:
            raise SqlTicketNotFoundError()
        reply = TicketMessage(
            ticket_id=ticket.id,
            sender_id=principal.user_id,
            message=masked,
            email_status="pending",
        )
        session.add(reply)
        if principal.user_id == ticket.instructor_id and ticket.first_response_at is None:
            ticket.first_response_at = _utcnow()
            if ticket.status == "open":
                ticket.status = "in_progress"
        recipient = session.get(
            User, ticket.student_id if principal.user_id == ticket.instructor_id else ticket.instructor_id
        )
        session.flush()
        reply_id = reply.id
        recipient_email = recipient.email if recipient is not None else ""
    status = _notify(recipient_email, "CodeForge support reply", masked) if recipient_email else "unconfigured"
    with session_scope() as session:
        stored = session.get(TicketMessage, reply_id)
        if stored is not None:
            stored.email_status = status
    return get_ticket(ticket_id)


def load_escalation_state(conversation_id: str) -> dict[str, int]:
    with session_scope() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None or not conversation.escalation_state_json:
            return {"consecutive_negative": 0, "repair_failures": 0, "policy_denials": 0}
        try:
            raw = json.loads(conversation.escalation_state_json)
        except json.JSONDecodeError:
            raw = {}
    return {
        "consecutive_negative": int(raw.get("consecutive_negative") or 0),
        "repair_failures": int(raw.get("repair_failures") or 0),
        "policy_denials": int(raw.get("policy_denials") or 0),
    }


def save_escalation_state(conversation_id: str, state: dict[str, int]) -> None:
    with session_scope() as session:
        conversation = session.get(Conversation, conversation_id)
        if conversation is None:
            return
        conversation.escalation_state_json = json.dumps(state)


def student_message(ticket: dict[str, Any]) -> str:
    return (
        "I've passed this issue to a CodeForge instructor. "
        f"Your support ticket is {ticket['id']}. "
        "An instructor is expected to respond within 4 hours. "
        "I've shared your original request, code and troubleshooting history, "
        "so you won't need to repeat yourself."
    )
