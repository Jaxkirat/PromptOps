"""Ticket authorization port.

Persisted rows in ``tickets`` are the assignment source. Automatic R3 escalation
is not implemented: a ticket exists only when a row is stored. ``status='open'``
means the instructor in ``instructor_id`` may see that handoff. Resolved tickets
and other instructors' tickets are omitted. Tests can still install
``InMemoryTicketAccess``.
"""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
from typing import Iterator, Protocol

from codeforge.sql_agent.models import TicketGrant


class TicketAccessPort(Protocol):
    def r3_available(self) -> bool:
        """True only when a real assignment source is connected."""

    def grants_for_instructor(self, instructor_id: str) -> tuple[TicketGrant, ...]:
        """Currently assigned tickets for this instructor. Closed tickets are omitted."""


class DatabaseTicketAccess:
    """Read open tickets from the application database at query time."""

    def r3_available(self) -> bool:
        return True

    def grants_for_instructor(self, instructor_id: str) -> tuple[TicketGrant, ...]:
        from codeforge.database.database import session_scope
        from codeforge.database.models import Message, Run, Ticket

        with session_scope() as session:
            tickets = (
                session.query(Ticket)
                .filter(Ticket.instructor_id == instructor_id, Ticket.status.in_(("open", "in_progress")))
                .all()
            )
            grants: list[TicketGrant] = []
            for ticket in tickets:
                run_ids: list[str] = []
                request = ticket.handoff_note
                if ticket.run_id:
                    run = session.get(Run, ticket.run_id)
                    if run is not None and run.user_id == ticket.student_id:
                        request = run.sanitised_request
                        if run.conversation_id:
                            siblings = (
                                session.query(Run.id)
                                .filter(
                                    Run.user_id == ticket.student_id,
                                    Run.conversation_id == run.conversation_id,
                                )
                                .all()
                            )
                            run_ids.extend(row[0] for row in siblings)
                        if ticket.run_id not in run_ids:
                            run_ids.append(ticket.run_id)
                attempts = (
                    session.query(Message)
                    .filter(Message.run_id.in_(run_ids), Message.role == "user")
                    .count()
                    if run_ids
                    else 1
                )
                grants.append(
                    build_grant(
                        ticket_id=ticket.id,
                        instructor_id=ticket.instructor_id,
                        student_id=ticket.student_id,
                        run_ids=tuple(run_ids),
                        priority=ticket.priority,
                        created_at=ticket.created_at.isoformat() if ticket.created_at else "",
                        sla_status=ticket.status,
                        sanitised_request=request,
                        handoff_summary=ticket.handoff_note,
                        attempts=attempts or 1,
                        last_failing_test=ticket.last_failing_test,
                        status="assigned",
                    )
                )
            return tuple(grants)


class UnavailableTicketAccess:
    """Fail closed. An instructor role alone grants no student rows."""

    def r3_available(self) -> bool:
        return False

    def grants_for_instructor(self, instructor_id: str) -> tuple[TicketGrant, ...]:
        del instructor_id
        return ()


class InMemoryTicketAccess:
    """Fixture port. Reassignment replaces the instructor checked on the next query."""

    def __init__(self) -> None:
        self._grants: dict[str, TicketGrant] = {}

    def r3_available(self) -> bool:
        return True

    def put(self, grant: TicketGrant) -> None:
        self._grants[grant.ticket_id] = grant

    def reassign(self, ticket_id: str, instructor_id: str) -> None:
        current = self._grants[ticket_id]
        self._grants[ticket_id] = TicketGrant(
            ticket_id=current.ticket_id,
            instructor_id=instructor_id,
            student_id=current.student_id,
            student_ref=current.student_ref,
            run_ids=current.run_ids,
            priority=current.priority,
            status="assigned",
            created_at=current.created_at,
            sla_status=current.sla_status,
            sanitised_request=current.sanitised_request,
            handoff_summary=current.handoff_summary,
            attempts=current.attempts,
            last_failing_test=current.last_failing_test,
        )

    def close(self, ticket_id: str) -> None:
        current = self._grants[ticket_id]
        self._grants[ticket_id] = TicketGrant(
            ticket_id=current.ticket_id,
            instructor_id=current.instructor_id,
            student_id=current.student_id,
            student_ref=current.student_ref,
            run_ids=current.run_ids,
            priority=current.priority,
            status="closed",
            created_at=current.created_at,
            sla_status=current.sla_status,
            sanitised_request=current.sanitised_request,
            handoff_summary=current.handoff_summary,
            attempts=current.attempts,
            last_failing_test=current.last_failing_test,
        )

    def grants_for_instructor(self, instructor_id: str) -> tuple[TicketGrant, ...]:
        return tuple(
            grant
            for grant in self._grants.values()
            if grant.instructor_id == instructor_id and grant.status == "assigned"
        )


_port: TicketAccessPort | None = None


def get_ticket_access() -> TicketAccessPort:
    return _port if _port is not None else DatabaseTicketAccess()


def set_ticket_access(port: TicketAccessPort | None) -> None:
    global _port
    _port = port


@contextmanager
def using_ticket_access(port: TicketAccessPort) -> Iterator[TicketAccessPort]:
    previous = _port
    set_ticket_access(port)
    try:
        yield port
    finally:
        set_ticket_access(previous)


def student_ref_for(student_id: str, ticket_id: str) -> str:
    """Pseudonym. It is not the user id, email, or name."""
    digest = hashlib.sha256(f"{student_id}:{ticket_id}".encode()).hexdigest()[:8]
    return f"stu-{digest}"


def build_grant(
    *,
    ticket_id: str,
    instructor_id: str,
    student_id: str,
    run_ids: tuple[str, ...],
    priority: str = "normal",
    created_at: str = "",
    sla_status: str = "within_sla",
    sanitised_request: str = "",
    handoff_summary: str = "",
    attempts: int = 1,
    last_failing_test: str = "",
    status: str = "assigned",
) -> TicketGrant:
    return TicketGrant(
        ticket_id=ticket_id,
        instructor_id=instructor_id,
        student_id=student_id,
        student_ref=student_ref_for(student_id, ticket_id),
        run_ids=tuple(run_ids),
        priority=priority,
        status=status,
        created_at=created_at,
        sla_status=sla_status,
        sanitised_request=sanitised_request,
        handoff_summary=handoff_summary,
        attempts=attempts,
        last_failing_test=last_failing_test,
    )
