"""R3 and R4 golden executors."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from codeforge.escalation.rules import next_negative_count, should_escalate
from codeforge.escalation.triage import TriageResult, triage_text
from codeforge.evals.harness import EvalHarness


def _triage(**kwargs) -> TriageResult:
    return TriageResult(**kwargs)


def esc_calm(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    if should_escalate(_triage(), 0, 0, 0).should_escalate:
        raise AssertionError("a calm turn escalated")


def esc_human(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    decision = should_escalate(triage_text("I want to talk to an instructor."), 0, 0, 0)
    if not decision.should_escalate or decision.priority != "P1" or decision.sla_hours != 4:
        raise AssertionError("explicit human request did not create a P1 decision")


def esc_angry(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    decision = should_escalate(triage_text("this is unacceptable"), 0, 0, 0)
    if decision.trigger_reason != "angry_sentiment":
        raise AssertionError("angry sentiment did not escalate")


def esc_two_negative(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    first = next_negative_count(0, triage_text("This isn't quite what I expected.").sentiment)
    if should_escalate(triage_text("This isn't quite what I expected."), first, 0, 0).should_escalate:
        raise AssertionError("the first negative turn escalated")
    second = next_negative_count(first, "negative")
    if should_escalate(_triage(sentiment="negative"), second, 0, 0).trigger_reason != "two_negative":
        raise AssertionError("two negative turns did not escalate")


def esc_repairs(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    if should_escalate(_triage(), 0, 2, 0).trigger_reason != "repair_failures":
        raise AssertionError("two repair failures did not escalate")


def esc_denials(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    if should_escalate(_triage(), 0, 0, 2).trigger_reason != "policy_denials":
        raise AssertionError("two policy denials did not escalate")


def esc_separate(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    if should_escalate(_triage(), 0, 0, 1).should_escalate or should_escalate(_triage(), 0, 0, 1).should_escalate:
        raise AssertionError("denials from separate conversations were combined")


def esc_reset(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    if next_negative_count(2, "neutral") != 0:
        raise AssertionError("a neutral turn did not reset the counter")


def assign_round_robin(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from codeforge.database.database import session_scope
    from codeforge.escalation.service import assign_next_instructor

    harness.register_instructor("rr1")
    harness.register_instructor("rr2")
    with session_scope() as session:
        first = assign_next_instructor(session)
        second = assign_next_instructor(session)
    if not first or not second or first == second:
        raise AssertionError("round-robin did not rotate instructors")


def assign_inactive(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from codeforge.database.database import session_scope
    from codeforge.database.models import User
    from codeforge.escalation.service import assign_next_instructor

    _token, inactive_id = harness.register_instructor("inactive")
    with session_scope() as session:
        session.get(User, inactive_id).is_active = False
    with session_scope() as session:
        chosen = assign_next_instructor(session)
    if chosen == inactive_id:
        raise AssertionError("an inactive instructor was assigned")


def assign_none(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from codeforge.database.database import session_scope
    from codeforge.database.models import User
    from codeforge.escalation.service import assign_next_instructor

    with session_scope() as session:
        previous = [(user.id, user.is_active) for user in session.query(User).filter(User.role == "instructor")]
        for user_id, _active in previous:
            session.get(User, user_id).is_active = False
    try:
        with session_scope() as session:
            if assign_next_instructor(session) is not None:
                raise AssertionError("a missing instructor pool still assigned someone")
    finally:
        with session_scope() as session:
            for user_id, active in previous:
                session.get(User, user_id).is_active = active


def handoff_masked(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    from codeforge.database.models import Run
    from codeforge.escalation.rules import EscalationDecision
    from codeforge.escalation.service import build_handoff

    note, _failing = build_handoff(
        Run(user_id="u", sanitised_request="reach ada@example.com", status="tests_failed"),
        EscalationDecision(should_escalate=True, trigger_reason="explicit_human"),
    )
    if "ada@example.com" in note or "[SECRET]" not in note:
        raise AssertionError("handoff was not sanitized")


def duplicate_ticket(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from tests.conftest import auth_header

    token, _user = harness.register_student("dup")
    harness.register_instructor("dupi")
    headers = auth_header(token)
    first = harness.client.post(
        "/api/v1/runs", json={"request": "I want to talk to an instructor."}, headers=headers
    )
    if first.status_code != 201:
        raise AssertionError(first.text)
    conversation_id = first.json()["artifacts"]["conversation_id"]
    second = harness.client.post(
        "/api/v1/runs",
        json={"request": "I want a human to look at this", "conversation_id": conversation_id},
        headers=headers,
    )
    if first.json()["artifacts"]["ticket"]["id"] != second.json()["artifacts"]["ticket"]["id"]:
        raise AssertionError("a second escalation created another ticket")


def _ticket_parties(harness: EvalHarness, student_token: str):
    from codeforge.database.database import session_scope
    from codeforge.database.models import Ticket, User
    from tests.conftest import auth_header

    created = harness.client.post(
        "/api/v1/runs",
        json={"request": "I want to talk to an instructor."},
        headers=auth_header(student_token),
    )
    if created.status_code != 201 or "ticket" not in created.json().get("artifacts", {}):
        raise AssertionError(created.text)
    ticket_id = created.json()["artifacts"]["ticket"]["id"]
    with session_scope() as session:
        ticket = session.get(Ticket, ticket_id)
        assigned = session.get(User, ticket.instructor_id)
        other = (
            session.query(User)
            .filter(User.role == "instructor", User.id != ticket.instructor_id, User.is_active.is_(True))
            .first()
        )
        assigned_email = assigned.email
        other_email = other.email if other is not None else ""
    assigned_token = harness.client.post(
        "/api/v1/auth/login",
        json={"email": assigned_email, "password": "StrongPassword123"},
    ).json()["access_token"]
    other_token = ""
    if other_email:
        other_token = harness.client.post(
            "/api/v1/auth/login",
            json={"email": other_email, "password": "StrongPassword123"},
        ).json()["access_token"]
    return ticket_id, assigned_token, other_token


def auth_assigned(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from tests.conftest import auth_header

    token, _user = harness.register_student("owner")
    harness.register_instructor("ownerinst")
    ticket_id, assigned_token, _other = _ticket_parties(harness, token)
    seen = harness.client.get(f"/api/v1/support/tickets/{ticket_id}", headers=auth_header(assigned_token))
    if seen.status_code != 200:
        raise AssertionError("assigned instructor could not view the ticket")


def auth_unassigned(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from tests.conftest import auth_header

    token, _user = harness.register_student("hidden")
    harness.register_instructor("assigned")
    harness.register_instructor("other")
    ticket_id, _assigned, other_token = _ticket_parties(harness, token)
    if not other_token:
        raise AssertionError("no second instructor was available")
    seen = harness.client.get(f"/api/v1/support/tickets/{ticket_id}", headers=auth_header(other_token))
    if seen.status_code != 404:
        raise AssertionError("another instructor could view the ticket")


def reply_visible(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from codeforge.escalation.service import set_email_sender
    from tests.conftest import auth_header

    token, _user = harness.register_student("reply")
    harness.register_instructor("replyinst")
    ticket_id, assigned_token, _other = _ticket_parties(harness, token)
    set_email_sender(lambda *_args: "sent")
    try:
        harness.client.post(
            f"/api/v1/support/tickets/{ticket_id}/replies",
            json={"message": "Try the empty input."},
            headers=auth_header(assigned_token),
        )
    finally:
        set_email_sender(None)
    visible = harness.client.get(f"/api/v1/support/tickets/{ticket_id}", headers=auth_header(token))
    if "Try the empty input." not in visible.text:
        raise AssertionError("the student could not see the instructor reply")


def first_response(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from tests.conftest import auth_header

    token, _user = harness.register_student("sla")
    harness.register_instructor("slainst")
    ticket_id, assigned_token, _other = _ticket_parties(harness, token)
    replied = harness.client.post(
        f"/api/v1/support/tickets/{ticket_id}/replies",
        json={"message": "Looking now."},
        headers=auth_header(assigned_token),
    )
    if not replied.json().get("first_response_at"):
        raise AssertionError("the first instructor response was not recorded")


def email_failure(harness: EvalHarness, _case: dict[str, Any]) -> None:
    from codeforge.escalation.service import set_email_sender
    from tests.conftest import auth_header

    token, _user = harness.register_student("mail")
    harness.register_instructor("mailinst")
    ticket_id, assigned_token, _other = _ticket_parties(harness, token)
    set_email_sender(lambda *_args: (_ for _ in ()).throw(RuntimeError("smtp down")))
    try:
        replied = harness.client.post(
            f"/api/v1/support/tickets/{ticket_id}/replies",
            json={"message": "Still saved."},
            headers=auth_header(assigned_token),
        )
    finally:
        set_email_sender(None)
    body = replied.json()
    if body["replies"][0]["email_status"] != "failed" or "Still saved." not in body["replies"][0]["message"]:
        raise AssertionError("an email failure dropped the in-app reply")


def cache_isolation(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    from codeforge.cost.cache import SemanticCache

    cache = SemanticCache()
    cache.put("Write a Python function that checks a palindrome.", "code-a", language="python", task_type="code_generation")
    if cache.get("fix this error in my code", language="python", task_type="code_generation"):
        raise AssertionError("a contextual request hit the cache")
    if cache.get("Write a Python function that checks a palindrome.", language="python", task_type="code_generation", ) != "code-a":
        raise AssertionError("a safe repeat missed the cache")


def cache_secret(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    from codeforge.cost.cache import is_cacheable

    if is_cacheable("token sk-synthetickey123456", redactions=1):
        raise AssertionError("a secret request was cacheable")


def cache_guards(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    from codeforge.cost.cache import SemanticCache

    cache = SemanticCache()
    cache.put("Sort a list ascending.", "up", language="python", task_type="code_generation")
    if cache.get("Sort a list descending.", language="python", task_type="code_generation"):
        raise AssertionError("an answer-changing request matched the cache")


def r4_route(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    from codeforge.cost.cascade import tier_for

    if tier_for("router") != "small" or tier_for("code_generation") != "large":
        raise AssertionError("cascade tiers are wrong")


def r4_compact(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    from codeforge.cost.compact import compact_messages

    messages = [{"role": "user", "content": "The function must return a list."}]
    messages.extend({"role": "user", "content": f"note {index}"} for index in range(9))
    compacted, changed = compact_messages(messages)
    if not changed or "must return a list" not in compacted[0]["content"]:
        raise AssertionError("compaction dropped the constraint")


def r4_cost(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    from codeforge.cost.pricing import estimate_cost_usd

    if estimate_cost_usd("missing-model", 10, 10) is not None:
        raise AssertionError("missing pricing was reported as a number")


def r4_usage(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    from codeforge.cost.meter import UsageMeter

    meter = UsageMeter(agent="router")

    class Message:
        usage_metadata = {"input_tokens": 3, "output_tokens": 2}
        response_metadata = {"model_name": "demo"}

    class Generation:
        message = Message()

    class Response:
        generations = [[Generation()]]

    meter.on_chat_model_start({}, [], run_id="one")
    meter.on_llm_end(Response(), run_id="one")
    summary = meter.summary()["agents"]["router"]
    if summary["input_tokens"] != 3 or summary["usage_source"] != "provider":
        raise AssertionError("provider usage was not aggregated")


def r7_escalation_available(harness: EvalHarness, _case: dict[str, Any]) -> None:
    del harness
    import codeforge.escalation as escalation

    if not hasattr(escalation, "should_escalate"):
        raise AssertionError("escalation is not available")
    if not should_escalate(triage_text("I want a human"), 0, 0, 0).should_escalate:
        raise AssertionError("a human request did not escalate")


R34_EXECUTORS = {
    "S-ESC-001": esc_calm,
    "S-ESC-002": esc_human,
    "S-ESC-003": esc_angry,
    "S-ESC-004": esc_two_negative,
    "S-ESC-005": esc_repairs,
    "S-ESC-006": esc_denials,
    "S-ESC-007": esc_separate,
    "S-R7-R3-001": r7_escalation_available,
    "H-R3-ESC-001": esc_human,
    "H-R3-ESC-002": esc_angry,
    "H-R3-ESC-003": esc_two_negative,
    "H-R3-ESC-004": esc_calm,
    "H-R3-ESC-005": esc_repairs,
    "H-R3-ESC-006": esc_denials,
    "H-R3-ESC-007": esc_separate,
    "H-R3-ESC-008": esc_reset,
    "H-R3-ASSIGN-001": assign_round_robin,
    "H-R3-ASSIGN-002": assign_inactive,
    "H-R3-ASSIGN-003": assign_none,
    "H-R3-PRIV-001": handoff_masked,
    "H-R3-DUP-001": duplicate_ticket,
    "H-R3-AUTH-001": auth_assigned,
    "H-R3-AUTH-002": auth_unassigned,
    "H-R3-REPLY-001": reply_visible,
    "H-R3-REPLY-002": first_response,
    "H-R3-EMAIL-001": email_failure,
    "H-R4-CACHE-001": cache_isolation,
    "H-R4-CACHE-002": cache_secret,
    "H-R4-CACHE-003": cache_guards,
    "S-R4-ROUTE-001": r4_route,
    "S-R4-COMPACT-001": r4_compact,
    "S-R4-COST-001": r4_cost,
    "S-R4-USAGE-001": r4_usage,
}
