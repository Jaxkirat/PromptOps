"""Deterministic R3 rules and ticket behavior. No live model."""

from uuid import uuid4

from codeforge.auth.identity import AuthenticatedPrincipal, principal_context
from codeforge.database.database import session_scope
from codeforge.database.models import User
from codeforge.escalation.rules import next_negative_count, should_escalate
from codeforge.escalation.service import assign_next_instructor, open_ticket, post_reply, set_email_sender
from codeforge.escalation.triage import TriageResult, triage_text
from codeforge.services.auth_service import provision_instructor
from tests.conftest import auth_header, register_and_login


def _decision(**kwargs):
    triage = TriageResult(**kwargs)
    return should_escalate(triage, kwargs.pop("negative", 0) if False else 0, 0, 0)


def test_explicit_human_and_angry_are_immediate():
    human = should_escalate(TriageResult(wants_human=True, sentiment="neutral"), 0, 0, 0)
    angry = should_escalate(TriageResult(sentiment="angry"), 0, 0, 0)
    calm = should_escalate(TriageResult(sentiment="neutral"), 0, 0, 0)
    assert human.should_escalate and human.priority == "P1" and human.sla_hours == 4
    assert human.trigger_reason == "explicit_human"
    assert angry.trigger_reason == "angry_sentiment"
    assert calm.should_escalate is False


def test_two_negative_turns_then_reset():
    assert next_negative_count(0, "negative") == 1
    assert should_escalate(TriageResult(sentiment="negative"), 1, 0, 0).should_escalate is False
    assert should_escalate(TriageResult(sentiment="negative"), 2, 0, 0).trigger_reason == "two_negative"
    assert next_negative_count(2, "neutral") == 0
    assert next_negative_count(2, "positive") == 0


def test_repairs_and_denials_are_scoped_by_the_caller():
    assert should_escalate(TriageResult(), 0, 2, 0).trigger_reason == "repair_failures"
    assert should_escalate(TriageResult(), 0, 1, 2).trigger_reason == "policy_denials"
    assert should_escalate(TriageResult(), 0, 1, 1).should_escalate is False


def test_keyword_triage_matches_the_examples():
    assert triage_text("I want to talk to an instructor.").wants_human is True
    assert triage_text("this is unacceptable").sentiment == "angry"
    assert triage_text("This isn't quite what I expected.").sentiment == "negative"
    assert triage_text("please add a function").sentiment == "neutral"
    assert triage_text("please add a function").wants_human is False


def test_round_robin_skips_inactive_and_persists(client):
    suffix = uuid4().hex[:8]
    first = provision_instructor(f"r3a-{suffix}@example.com", "StrongPassword123", "Instructor A")
    skipped = provision_instructor(f"r3b-{suffix}@example.com", "StrongPassword123", "Instructor B")
    third = provision_instructor(f"r3c-{suffix}@example.com", "StrongPassword123", "Instructor C")
    with session_scope() as session:
        inactive = session.get(User, skipped.id)
        inactive.is_active = False
    with session_scope() as session:
        one = assign_next_instructor(session)
        two = assign_next_instructor(session)
        three = assign_next_instructor(session)
    assert skipped.id not in {one, two, three}
    assert {one, two} == {first.id, third.id}
    assert three == one


def test_no_instructor_leaves_the_ticket_unassigned(client):
    token = register_and_login(client, f"solo-{uuid4().hex[:8]}@example.com")
    response = client.post(
        "/api/v1/runs",
        json={"request": "I want to talk to an instructor."},
        headers=auth_header(token),
    )
    assert response.status_code == 201, response.text
    ticket = response.json()["artifacts"]["ticket"]
    assert ticket["priority"] == "P1"
    assert ticket["status"] == "awaiting_assignment"
    assert "4 hours" in response.json()["artifacts"]["status_detail"]


def test_assigned_instructor_can_reply_and_email_failure_keeps_the_message(client):
    suffix = uuid4().hex[:8]
    student = register_and_login(client, f"stu-{suffix}@example.com")
    instructor = provision_instructor(f"inst-{suffix}@example.com", "StrongPassword123", "Instructor")
    created = client.post(
        "/api/v1/runs",
        json={"request": "Please connect me to someone."},
        headers=auth_header(student),
    )
    ticket_id = created.json()["artifacts"]["ticket"]["id"]
    login = client.post(
        "/api/v1/auth/login",
        json={"email": instructor.email, "password": "StrongPassword123"},
    )
    instructor_token = login.json()["access_token"]
    set_email_sender(lambda *_args: "failed")
    try:
        replied = client.post(
            f"/api/v1/support/tickets/{ticket_id}/replies",
            json={"message": "Look at the last assertion."},
            headers=auth_header(instructor_token),
        )
    finally:
        set_email_sender(None)
    assert replied.status_code == 200, replied.text
    body = replied.json()
    assert body["first_response_at"]
    assert body["replies"][0]["message"] == "Look at the last assertion."
    assert body["replies"][0]["email_status"] == "failed"
    assert instructor.email not in replied.text
    other = register_and_login(client, f"other-{suffix}@example.com")
    hidden = client.get(f"/api/v1/support/tickets/{ticket_id}", headers=auth_header(other))
    assert hidden.status_code == 404
    visible = client.get(f"/api/v1/support/tickets/{ticket_id}", headers=auth_header(student))
    assert visible.status_code == 200
    assert "Look at the last assertion." in visible.text


def test_duplicate_escalation_reuses_the_ticket(client):
    token = register_and_login(client, f"dup-{uuid4().hex[:8]}@example.com")
    provision_instructor(f"dupi-{uuid4().hex[:8]}@example.com", "StrongPassword123", "Instructor")
    first = client.post(
        "/api/v1/runs",
        json={"request": "Can a human help me?"},
        headers=auth_header(token),
    ).json()
    second = client.post(
        "/api/v1/runs",
        json={
            "request": "I want a human to look at this",
            "conversation_id": first["artifacts"]["conversation_id"],
        },
        headers=auth_header(token),
    ).json()
    assert first["artifacts"]["ticket"]["id"] == second["artifacts"]["ticket"]["id"]


def test_handoff_masks_email():
    from codeforge.database.models import Run
    from codeforge.escalation.rules import EscalationDecision
    from codeforge.escalation.service import build_handoff

    note, _failing = build_handoff(
        Run(user_id="u", sanitised_request="email ada@example.com broke the tests", status="tests_failed"),
        EscalationDecision(should_escalate=True, trigger_reason="repair_failures"),
    )
    assert "ada@example.com" not in note
    assert "[SECRET]" in note
