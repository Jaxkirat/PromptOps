"""Natural-language questions against persisted CodeForge rows.

The proposer is the deterministic fixture. Validation and execution are real.
"""

from uuid import uuid4

from codeforge.database.database import session_scope
from codeforge.database.models import Run, Ticket, TicketMessage
from codeforge.services.auth_service import provision_instructor
from codeforge.sql_agent.integrity import storage_fingerprint
from tests.conftest import auth_header


def _register(client, email: str, name: str) -> tuple[str, str]:
    created = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPassword123", "full_name": name},
    )
    assert created.status_code == 201, created.text
    logged = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123"},
    )
    assert logged.status_code == 200, logged.text
    body = logged.json()
    return body["access_token"], body["user"]["id"]


def _ask(client, token: str, question: str, ticket_id: str | None = None):
    return client.post(
        "/api/v1/sql/query",
        json={"question": question, "ticket_id": ticket_id},
        headers=auth_header(token),
    )


def test_students_and_instructors_use_persisted_rows(client):
    suffix = uuid4().hex[:8]
    alpha_token, alpha_id = _register(client, f"alpha-{suffix}@example.com", "Row Alpha")
    beta_token, beta_id = _register(client, f"beta-{suffix}@example.com", "Row Beta")
    instructor = provision_instructor(f"ia-{suffix}@example.com", "StrongPassword123", "Instructor Alpha")
    other = provision_instructor(f"ib-{suffix}@example.com", "StrongPassword123", "Instructor Beta")
    instructor_email = instructor.email
    other_email = other.email
    other_id = other.id
    alpha_run = client.post(
        "/api/v1/runs",
        json={"request": "Write a palindrome function for alpha"},
        headers=auth_header(alpha_token),
    )
    assert alpha_run.status_code == 201, alpha_run.text
    beta_run = client.post(
        "/api/v1/runs",
        json={"request": "Write a factorial function for beta"},
        headers=auth_header(beta_token),
    )
    assert beta_run.status_code == 201, beta_run.text
    with session_scope() as session:
        stored = session.get(Run, alpha_run.json()["id"])
        assert stored is not None and stored.conversation_id
        stored.status = "tests_failed"
        stored.language = "python"
        stored.generated_code = "def is_palindrome(text):\n    return True\n"
        beta = session.get(Run, beta_run.json()["id"])
        assert beta is not None
        beta.language = "python"
        beta.status = "success"
        beta.generated_code = "def factorial(n):\n    return 1\n"
        ticket_a = Ticket(
            student_id=alpha_id,
            instructor_id=instructor.id,
            run_id=stored.id,
            priority="high",
            status="open",
            trigger_reason="tests_failed",
            handoff_note="Palindrome tests failed.",
            last_failing_test="test_palindrome",
        )
        ticket_b = Ticket(
            student_id=beta_id,
            instructor_id=other.id,
            run_id=beta.id,
            priority="normal",
            status="open",
            trigger_reason="review",
            handoff_note="Factorial review.",
            last_failing_test="test_factorial",
        )
        session.add(ticket_a)
        session.add(ticket_b)
        session.flush()
        session.add(
            TicketMessage(
                ticket_id=ticket_a.id,
                sender_id=instructor.id,
                message="Look at the last failing test.",
                email_status="failed",
            )
        )
        ticket_a_id = ticket_a.id
        ticket_b_id = ticket_b.id
    before = storage_fingerprint()
    prompts = _ask(client, alpha_token, "Show my last 10 prompts.").json()
    failed = _ask(client, alpha_token, "Show my failed runs.").json()
    code = _ask(client, alpha_token, "Show the generated code from my previous run.").json()
    blocked = _ask(client, alpha_token, "Show Student B's prompts.")
    assert prompts["ok"] is True and "palindrome" in str(prompts["rows"])
    assert "factorial" not in str(prompts["rows"])
    assert failed["ok"] is True and "tests_failed" in str(failed["rows"])
    assert code["ok"] is True and "is_palindrome" in str(code["rows"])
    assert blocked.json()["ok"] is False
    assert "factorial" not in blocked.text
    beta_prompts = _ask(client, beta_token, "Show my last 10 prompts.").json()
    assert "factorial" in str(beta_prompts["rows"]) and "palindrome" not in str(beta_prompts["rows"])

    instructor_token, _instructor_id = _login(client, instructor_email)
    other_token, other_id = _login(client, other_email)
    context = client.get(f"/api/v1/sql/tickets/{ticket_a_id}", headers=auth_header(instructor_token))
    assert context.status_code == 200, context.text
    assert "Row Alpha" not in context.text
    assert "@example.com" not in context.text
    assert "test_palindrome" in context.text
    original = _ask(client, instructor_token, "What was the original request?", ticket_a_id).json()
    generated = _ask(client, instructor_token, "Show the generated code for this handoff.", ticket_a_id).json()
    attempts = _ask(client, instructor_token, "Show the previous attempts associated with this ticket.", ticket_a_id).json()
    failing = _ask(client, instructor_token, "Which test failed last?", ticket_a_id).json()
    assert original["ok"] and "palindrome" in str(original["rows"])
    assert generated["ok"] and "is_palindrome" in str(generated["rows"])
    assert attempts["ok"] and "factorial" not in str(attempts["rows"])
    assert failing["ok"] and "test_palindrome" in str(failing["rows"])
    foreign_ticket = _ask(client, instructor_token, "What was the original request?", ticket_b_id)
    assert foreign_ticket.status_code == 404
    unrelated = _ask(client, instructor_token, "Show my last 10 prompts.").json()
    assert "factorial" not in str(unrelated.get("rows"))
    assert "palindrome" not in str(unrelated.get("rows"))

    with session_scope() as session:
        ticket = session.get(Ticket, ticket_a_id)
        assert ticket is not None
        ticket.instructor_id = other_id
    revoked = _ask(client, instructor_token, "What was the original request?", ticket_a_id)
    assert revoked.status_code == 404
    gained = _ask(client, other_token, "Which test failed last?", ticket_a_id).json()
    assert gained["ok"] is True and "test_palindrome" in str(gained["rows"])
    assert storage_fingerprint() == before


def _login(client, email: str) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body["access_token"], body["user"]["id"]
