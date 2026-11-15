"""Approval permissions, races, and the rule that approval cannot override deny."""

import threading

import pytest

from codeforge.auth.identity import AuthenticatedPrincipal, principal_context
from codeforge.database.database import session_scope
from codeforge.database.models import ApprovalRequest
from codeforge.exceptions import ApprovalConflictError, ApprovalNotFoundError, AuthorizationError
from codeforge.services.approval_service import create_approval, decide, get_approval, list_pending
from codeforge.services.auth_service import provision_instructor, register_student


def _principal(user, role: str) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user_id=user.id, role=role, email=user.email, is_active=True
    )


def _pending(owner_id: str) -> str:
    return create_approval(
        user_id=owner_id,
        run_id=None,
        thread_id="thread-1",
        reasons=["open()"],
        operations=["open"],
        code_text="def read():\n    return open('a').read()\n",
        tests_text="def test_x():\n    assert True\n",
        summary="read a file",
    )


def test_student_cannot_approve_or_list(api_env, monkeypatch):
    student = register_student("student@example.com", "StrongPassword123", "Stu")
    instructor = provision_instructor("prof@example.com", "StrongPassword123", "Prof")
    approval_id = _pending(student.id)
    monkeypatch.setattr(
        "codeforge.services.approval_service.resume_graph",
        lambda thread_id, resume: {"report": None},
    )

    with principal_context(_principal(student, "student")):
        with pytest.raises(AuthorizationError):
            list_pending()
        with pytest.raises(AuthorizationError):
            decide(approval_id, "approved")

    with principal_context(_principal(instructor, "instructor")):
        rows = list_pending()
        assert [row["id"] for row in rows] == [approval_id]
        decided = decide(approval_id, "rejected")
        assert decided["status"] == "rejected"

    with principal_context(_principal(instructor, "instructor")):
        with pytest.raises(ApprovalConflictError):
            decide(approval_id, "approved")


def test_other_student_cannot_see_the_request(api_env):
    owner = register_student("owner@example.com", "StrongPassword123", "Own")
    other = register_student("other@example.com", "StrongPassword123", "Other")
    approval_id = _pending(owner.id)
    with principal_context(_principal(other, "student")):
        with pytest.raises(ApprovalNotFoundError):
            get_approval(approval_id)
        with pytest.raises(ApprovalNotFoundError):
            decide(approval_id, "rejected")


def test_only_one_instructor_wins_a_race(api_env, monkeypatch):
    student = register_student("race-student@example.com", "StrongPassword123", "Stu")
    first = provision_instructor("race-a@example.com", "StrongPassword123", "A")
    second = provision_instructor("race-b@example.com", "StrongPassword123", "B")
    approval_id = _pending(student.id)
    monkeypatch.setattr(
        "codeforge.services.approval_service.resume_graph",
        lambda thread_id, resume: {"report": None},
    )
    outcomes: list[str] = []

    def attempt(user):
        try:
            with principal_context(_principal(user, "instructor")):
                decide(approval_id, "approved")
            outcomes.append("won")
        except ApprovalConflictError:
            outcomes.append("lost")

    threads = [threading.Thread(target=attempt, args=(user,)) for user in (first, second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert outcomes.count("won") == 1
    assert outcomes.count("lost") == 1
    with session_scope() as db:
        row = db.get(ApprovalRequest, approval_id)
        assert row is not None
        assert row.status == "approved"


def test_expired_approval_cannot_be_decided(api_env):
    from datetime import datetime, timedelta, timezone

    student = register_student("old-student@example.com", "StrongPassword123", "Stu")
    instructor = provision_instructor("old-prof@example.com", "StrongPassword123", "Prof")
    approval_id = _pending(student.id)
    with session_scope() as db:
        row = db.get(ApprovalRequest, approval_id)
        row.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5)
    with principal_context(_principal(instructor, "instructor")):
        with pytest.raises(ApprovalConflictError):
            decide(approval_id, "approved")
