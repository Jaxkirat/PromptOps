"""Student and instructor scope, privacy, and the disabled switch."""

from datetime import datetime, timezone
from uuid import uuid4

from codeforge.config.settings import get_settings
from codeforge.database.database import session_scope
from codeforge.database.models import Run, SqlQueryAudit
from codeforge.services.auth_service import provision_instructor
from codeforge.services.user_service import UserProfile
from codeforge.sql_agent.allowlist import SAMPLE_TABLES, STUDENT_TABLES, schema_text
from codeforge.sql_agent.integrity import storage_fingerprint
from codeforge.sql_agent.proposer import FixedSqlProposer, set_sql_proposer
from codeforge.sql_agent.sample_db import SAMPLE_SECRETS
from codeforge.sql_agent.tickets import build_grant, get_ticket_access, using_ticket_access
from codeforge.ui.handlers import (
    handle_instructor_sql,
    handle_refresh_tickets,
    handle_student_sql,
    new_session,
)
from tests.conftest import auth_header, register_and_login


def _login(client, email: str) -> tuple[str, str]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "StrongPassword123"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body["access_token"], body["user"]["id"]


def _run(client, token: str, text: str) -> dict:
    response = client.post("/api/v1/runs", json={"request": text}, headers=auth_header(token))
    assert response.status_code == 201, response.text
    return response.json()


def _query(client, token: str, question: str, ticket_id: str | None = None):
    return client.post(
        "/api/v1/sql/query",
        json={"question": question, "ticket_id": ticket_id, "user_id": "ignored-client-id"},
        headers=auth_header(token),
    )


def test_schema_context_hides_users_and_credentials():
    text = schema_text(STUDENT_TABLES | SAMPLE_TABLES)
    assert "users" not in text
    assert "password" not in text
    assert "email" not in text
    assert "student_prompt_history" in text
    assert "sales" in text


def test_default_ticket_port_reads_persisted_assignments(client):
    port = get_ticket_access()
    assert port.r3_available() is True
    assert port.grants_for_instructor("does-not-exist") == ()


def test_own_history_cte_union_and_added_limit(client):
    suffix = uuid4().hex[:8]
    token, _user_id = _account(client, f"hist-{suffix}@example.com")
    _run(client, token, "Write a palindrome function called mine")
    own = _query(client, token, "Show my last 10 prompts.").json()
    assert own["ok"] is True
    assert own["validated_sql"] is None
    assert "palindrome" in str(own["rows"])
    cte = _query(
        client,
        token,
        "WITH totals AS (SELECT employee_id, SUM(amount) AS total FROM sales GROUP BY employee_id) "
        "SELECT employee_id, total FROM totals",
    ).json()
    union = _query(
        client,
        token,
        "SELECT region FROM sales UNION SELECT department FROM employees",
    ).json()
    limited = _query(client, token, "SELECT id, amount FROM sales").json()
    assert cte["ok"] is True and cte["row_count"] == 3
    assert union["ok"] is True and union["row_count"] >= 4
    assert limited["ok"] is True
    assert limited["limit_applied"] == 100
    assert limited["row_count"] == 4


def _register(client, email: str) -> str:
    created = client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": "StrongPassword123", "full_name": "Pat Example"},
    )
    assert created.status_code == 201, created.text
    return email


def _account(client, email: str) -> tuple[str, str]:
    return _login(client, _register(client, email))


def test_subquery_cte_and_join_stay_inside_the_student(client):
    suffix = uuid4().hex[:8]
    owner_token, _owner_id = _account(client, f"owner-{suffix}@example.com")
    other_token, _other_id = _account(client, f"other-{suffix}@example.com")
    _run(client, owner_token, "owner sentinel OWNER_ROW_77")
    other = _run(client, other_token, "other sentinel OTHER_ROW_88")
    statements = [
        "SELECT prompt FROM student_prompt_history WHERE run_id IN (SELECT run_id FROM student_prompt_history)",
        "WITH all_rows AS (SELECT prompt FROM student_prompt_history) SELECT prompt FROM all_rows",
        "SELECT p.prompt FROM student_prompt_history AS p JOIN student_run_history AS r ON p.run_id = r.run_id",
    ]
    for sql in statements:
        set_sql_proposer(FixedSqlProposer(sql))
        body = _query(client, owner_token, "Show my last 10 prompts.").json()
        assert body["ok"] is True, body
        rendered = str(body["rows"])
        assert "OWNER_ROW_77" in rendered
        assert "OTHER_ROW_88" not in rendered
    set_sql_proposer(None)
    foreign = _query(client, owner_token, f"Show prompts for run {other['id']}").json()
    assert foreign["ok"] is False
    assert foreign["rejection_category"] == "foreign_identifier"
    assert "OTHER_ROW_88" not in str(foreign)


def test_secret_is_redacted_from_results_audit_and_logs(client, caplog):
    import logging

    suffix = uuid4().hex[:8]
    token, user_id = _account(client, f"secret-{suffix}@example.com")
    run = _run(client, token, "Write a function that returns one")
    with session_scope() as session:
        stored = session.get(Run, run["id"])
        assert stored is not None
        stored.generated_code = "token = 'sk-synthetickey123456'\n"
    caplog.set_level(logging.INFO)
    before = storage_fingerprint()
    body = _query(client, token, "Show the generated code from my last run.").json()
    assert body["ok"] is True
    rendered = str(body)
    assert "sk-synthetickey123456" not in rendered
    assert "[SECRET]" in rendered
    asked = _query(client, token, "my key is sk-synthetickey123456").json()
    assert asked["ok"] is False
    assert asked["rejection_category"] == "pii_request"
    with session_scope() as session:
        audits = session.query(SqlQueryAudit).filter(SqlQueryAudit.user_id == user_id).all()
        blob = " ".join(row.sanitised_question + row.validated_sql for row in audits)
    assert "sk-synthetickey123456" not in blob
    assert "sk-synthetickey123456" not in caplog.text
    assert storage_fingerprint() == before


def test_instructor_ticket_scope_reassignment_and_privacy(client):
    suffix = uuid4().hex[:8]
    student_token, student_id = _account(client, f"stu-{suffix}@example.com")
    _account(client, f"stranger-{suffix}@example.com")
    run = _run(client, student_token, "Write a palindrome function for ticket alpha")
    stranger = client.post(
        "/api/v1/auth/login",
        json={"email": f"stranger-{suffix}@example.com", "password": "StrongPassword123"},
    )
    stranger_token = stranger.json()["access_token"]
    other_run = _run(client, stranger_token, "Write a factorial function for ticket beta")
    profile = client.get("/api/v1/users/me", headers=auth_header(student_token)).json()
    instructor_email = f"inst-{suffix}@example.com"
    other_email = f"inst2-{suffix}@example.com"
    provision_instructor(instructor_email, "StrongPassword123", "Instructor One")
    provision_instructor(other_email, "StrongPassword123", "Instructor Two")
    instructor_token, instructor_id = _login(client, instructor_email)
    other_token, other_id = _login(client, other_email)
    ticket_id = uuid4().hex
    from codeforge.sql_agent.tickets import InMemoryTicketAccess

    port = InMemoryTicketAccess()
    port.put(
        build_grant(
            ticket_id=ticket_id,
            instructor_id=instructor_id,
            student_id=student_id,
            run_ids=(run["id"],),
            created_at="2026-11-15T00:00:00",
            sanitised_request="Write a palindrome function for ticket alpha",
            handoff_summary="Palindrome attempt failed the last test.",
            last_failing_test="test_palindrome",
            attempts=2,
        )
    )
    with using_ticket_access(port):
        overview = client.get("/api/v1/sql/tickets", headers=auth_header(instructor_token))
        assert overview.status_code == 200, overview.text
        overview_text = overview.text
        assert overview.json()["r3_connected"] is True
        assert "palindrome" in overview_text
        assert profile["email"] not in overview_text
        assert "factorial" not in overview_text
        assert "stu-" in overview_text
        context = client.get(f"/api/v1/sql/tickets/{ticket_id}", headers=auth_header(instructor_token))
        assert context.status_code == 200, context.text
        assert profile["email"] not in context.text
        assert "Pat Example" not in context.text
        assert "test_palindrome" in context.text
        rows = _query(
            client,
            instructor_token,
            "SELECT prompt FROM student_prompt_history",
            ticket_id,
        ).json()
        assert rows["ok"] is True
        assert rows["validated_sql"]
        assert "palindrome" in str(rows["rows"])
        assert "factorial" not in str(rows["rows"])
        student_ticket = _query(client, student_token, "SELECT prompt FROM student_prompt_history", ticket_id)
        assert student_ticket.status_code == 403
        missing = _query(client, instructor_token, "Show the generated code for this ticket", uuid4().hex)
        assert missing.status_code == 404
        assert missing.json()["detail"] == "Ticket not found"
        outsider = _query(client, other_token, "SELECT prompt FROM student_prompt_history", ticket_id)
        assert outsider.status_code == 404
        closed_listing = client.get("/api/v1/sql/tickets", headers=auth_header(student_token))
        assert closed_listing.status_code == 403
        port.reassign(ticket_id, other_id)
        revoked = _query(client, instructor_token, "SELECT prompt FROM student_prompt_history", ticket_id)
        assert revoked.status_code == 404
        gained = _query(client, other_token, "SELECT prompt FROM student_prompt_history", ticket_id).json()
        assert gained["ok"] is True
        assert "palindrome" in str(gained["rows"])
        assert "factorial" not in str(gained["rows"])
        port.close(ticket_id)
        closed = _query(client, other_token, "SELECT prompt FROM student_prompt_history", ticket_id)
        assert closed.status_code == 404


def test_sql_agent_can_be_disabled(client, monkeypatch):
    monkeypatch.setenv("CODEFORGE_SQL_AGENT_ENABLED", "false")
    get_settings.cache_clear()
    token = register_and_login(client, f"off-{uuid4().hex[:8]}@example.com")
    response = _query(client, token, "Show my last 10 prompts.")
    assert response.status_code == 503
    from fastapi.testclient import TestClient

    from codeforge.api.main import create_application

    app = create_application()
    with TestClient(app) as probe:
        spec = probe.get("/openapi.json")
    assert spec.status_code == 200
    assert "/api/v1/runs" in spec.text
    assert "/api/v1/sql/query" in spec.text


def test_ui_does_not_trust_a_forged_role(client):
    suffix = uuid4().hex[:8]
    token, user_id = _account(client, f"ui-{suffix}@example.com")
    _run(client, token, "ui sentinel UI_OWNER_55")
    session = new_session()
    session["adapter"]._access_token = token
    session["profile"] = UserProfile(
        id=user_id,
        email=f"ui-{suffix}@example.com",
        full_name="Forged",
        role="instructor",
        is_active=True,
        created_at=datetime.now(timezone.utc),
    )
    history = handle_student_sql(session, "Show my last 10 prompts.")
    assert "UI_OWNER_55" in history
    denied = handle_instructor_sql(session, uuid4().hex, "Show the generated code for this ticket")
    assert "Students cannot query instructor tickets." in denied
    assert "UI_OWNER_55" not in denied
    tickets = handle_refresh_tickets(session)
    assert "Only instructors" in tickets
    assert handle_student_sql(new_session(), "Show my last 10 prompts.").startswith("Sign in")
