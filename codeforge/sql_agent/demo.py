"""Reproducible R7 demo.

The SQL proposer is the deterministic fixture, not a live model.
Instructor tickets come from an in-memory assignment port because R3 does not
persist handoff tickets. The validator and the read-only executor are the real ones.

    python -m codeforge.sql_agent.demo
"""

from __future__ import annotations

import os
from uuid import uuid4

os.environ["DATABASE_URL"] = "sqlite:///./demo_r7.sqlite"
os.environ["CODEFORGE_SQL_AGENT_ENABLED"] = "true"
os.environ["CODEFORGE_SQL_PROPOSER"] = "fixture"
os.environ["CODEFORGE_SQL_DIALECT"] = "sqlite"

from codeforge.config.settings import get_settings
from codeforge.database.database import init_db, session_scope
from codeforge.database.models import Run, Ticket
from codeforge.exceptions import SqlTicketNotFoundError
from codeforge.integration.codeforge_service import authenticated_context, login
from codeforge.services.auth_service import provision_instructor, register_student
from codeforge.sql_agent.integrity import storage_fingerprint
from codeforge.sql_agent.sample_db import SAMPLE_SECRETS
from codeforge.sql_agent.service import ask_sql, ticket_context

get_settings.cache_clear()


def main() -> int:
    """Run the student, instructor, attack and legitimate-query steps."""
    settings = get_settings()
    if not settings.jwt_secret_key:
        print("FAIL setup: JWT_SECRET_KEY is empty. The demo needs the normal app secret and will not print it.")
        return 1
    print("R7 demo uses the deterministic SQL fixture. It does not call a live model.")
    print("Tickets are rows in the application database. Automatic escalation is not implemented.")
    init_db()
    suffix = uuid4().hex[:8]
    student = register_student(f"demo-student-{suffix}@example.com", "StrongPassword123", "Demo Student")
    other = register_student(f"demo-other-{suffix}@example.com", "StrongPassword123", "Demo Other")
    instructor = provision_instructor(
        f"demo-instructor-{suffix}@example.com", "StrongPassword123", "Demo Instructor"
    )
    outsider = provision_instructor(
        f"demo-outsider-{suffix}@example.com", "StrongPassword123", "Demo Outsider"
    )
    with session_scope() as session:
        own = Run(
            user_id=student.id,
            sanitised_request="Write a palindrome function",
            status="tests_failed",
            task_type="python",
            language="python",
            generated_code="def is_palindrome(text):\n    return text == text[::-1]\n",
            generated_tests="def test_palindrome():\n    assert False\n",
        )
        foreign = Run(
            user_id=other.id,
            sanitised_request="Write a factorial function",
            status="success",
            task_type="python",
            language="python",
            generated_code="def factorial(n):\n    return 1\n",
        )
        session.add(own)
        session.add(foreign)
        session.flush()
        own_id = own.id
        foreign_id = foreign.id
        ticket = Ticket(
            student_id=student.id,
            instructor_id=instructor.id,
            run_id=own.id,
            priority="high",
            status="open",
            trigger_reason="tests_failed",
            handoff_note="The palindrome tests failed.",
            last_failing_test="test_palindrome",
        )
        session.add(ticket)
        session.flush()
        ticket_id = ticket.id
    failures: list[str] = []
    transcript: list[str] = []

    def record(name: str, passed: bool, detail: str) -> None:
        line = f"{'PASS' if passed else 'FAIL'} {name}: {detail}"
        transcript.append(line)
        print(line)
        if not passed:
            failures.append(name)

    student_token, _expires, student_profile = login(student.email, "StrongPassword123")
    record("student login", student_profile.role == "student", student_profile.role)
    with authenticated_context(student_token):
        own_rows = ask_sql("Show my last 10 prompts.")
        rendered = str(own_rows.rows)
        record(
            "own prompts",
            own_rows.ok and "palindrome" in rendered and "factorial" not in rendered,
            own_rows.message,
        )
        denied = ask_sql("Show me all students' prompts")
        record(
            "cross-user denied",
            (not denied.ok) and denied.rows == [] and "factorial" not in str(denied.rows),
            denied.message,
        )
    instructor_token, _expires, instructor_profile = login(instructor.email, "StrongPassword123")
    record("instructor login", instructor_profile.role == "instructor", instructor_profile.role)
    if ticket_id:
        with authenticated_context(instructor_token):
            context = ticket_context(ticket_id)
            context_text = str(context)
            record(
                "ticket context",
                "palindrome" in context_text
                and "test_palindrome" in context_text
                and student.email not in context_text
                and "Demo Student" not in context_text
                and "factorial" not in context_text
                and context["ticket"]["student_ref"].startswith("stu-"),
                f"ref {context['ticket']['student_ref']}",
            )
            attempts = ask_sql("Show the previous relevant attempts", ticket_id)
            attempt_text = str(attempts.rows)
            record(
                "assigned attempts",
                attempts.ok and "is_palindrome" in attempt_text and "factorial" not in attempt_text,
                attempts.message,
            )
        outsider_token, _expires, _outsider_profile = login(outsider.email, "StrongPassword123")
        with authenticated_context(outsider_token):
            try:
                ask_sql("SELECT prompt FROM student_prompt_history", ticket_id)
                record("unassigned denied", False, "query returned")
            except SqlTicketNotFoundError:
                record("unassigned denied", True, "Ticket not found")
        before = storage_fingerprint()
        with authenticated_context(student_token):
            blocked = ask_sql("DROP TABLE users")
            record(
                "drop blocked",
                (not blocked.ok) and blocked.executed is False and blocked.rows == [],
                blocked.message,
            )
            cte = ask_sql(
                "WITH totals AS (SELECT employee_id, SUM(amount) AS total FROM sales "
                "GROUP BY employee_id) SELECT employee_id, total FROM totals"
            )
            record("cte query", cte.ok and cte.row_count == 3, cte.message)
            union = ask_sql("SELECT region FROM sales UNION SELECT department FROM employees")
            record("union query", union.ok and union.row_count >= 4, union.message)
            clamped = ask_sql("SELECT id, amount FROM sales LIMIT 10000000")
            record(
                "limit clamped",
                clamped.ok and clamped.clamped and clamped.limit_applied == 500 and "10000000" not in clamped.message,
                f"limit {clamped.limit_applied}",
            )
        unchanged = storage_fingerprint() == before
        record("database unchanged", unchanged, "fingerprint matched" if unchanged else "fingerprint changed")
    leaked = [secret for secret in SAMPLE_SECRETS if any(secret in line for line in transcript)]
    record("no sample secrets printed", not leaked, "clean" if not leaked else "redacted output failed")
    if foreign_id == own_id:
        record("distinct runs", False, "ids collided")
    print(f"demo result: {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
