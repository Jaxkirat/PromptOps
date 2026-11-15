"""Gradio callback logic — talks only to GradioSessionAdapter / shared services.

No agent calls, no local masking, no local quota math, no role assignment.
"""

from __future__ import annotations

import json
import logging
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from codeforge.exceptions import (
    AuthenticationError,
    AuthorizationError,
    InvitationError,
    QuotaExceededError,
    RegistrationError,
    RunNotFoundError,
    SqlAgentDisabledError,
    SqlTicketNotFoundError,
)
from codeforge.integration.gradio_adapter import GradioSessionAdapter
from codeforge.services.quota_service import QuotaStatus
from codeforge.services.run_service import RunRecord
from codeforge.services.user_service import UserProfile
from codeforge.ui.formatters import (
    execution_report_json,
    sql_result_markdown,
    ticket_context_markdown,
    tickets_markdown,
)

logger = logging.getLogger(__name__)

EXAMPLE_PROMPTS = [
    "Write a Python function that checks whether a string is a palindrome.",
    "Write a function that computes the factorial of a non-negative integer.",
    "Write a function that finds duplicate values in a list.",
    "Write a function that sorts a list of tuples by a custom key (the second element).",
    "Write a function that returns the first n Fibonacci numbers as a list.",
]


def new_session() -> dict[str, Any]:
    """Independent per-browser-session state. Never stored globally."""
    return {
        "adapter": GradioSessionAdapter(),
        "profile": None,
        "conversation": [],
        "current_run": None,
    }


def ensure_session(session: dict[str, Any] | None) -> dict[str, Any]:
    """Return a valid session dict, creating a fresh one when needed."""
    if not isinstance(session, dict) or "adapter" not in session:
        return new_session()
    if not isinstance(session.get("adapter"), GradioSessionAdapter):
        session["adapter"] = GradioSessionAdapter()
    session.setdefault("conversation", [])
    session.setdefault("current_run", None)
    session.setdefault("profile", None)
    return session


def is_authenticated(session: dict[str, Any] | None) -> bool:
    session = session or {}
    adapter = session.get("adapter")
    return isinstance(adapter, GradioSessionAdapter) and adapter.is_authenticated


def _adapter(session: dict[str, Any]) -> GradioSessionAdapter:
    adapter = session.get("adapter")
    if not isinstance(adapter, GradioSessionAdapter):
        adapter = GradioSessionAdapter()
        session["adapter"] = adapter
    return adapter


def handle_login(
    session: dict[str, Any], email: str, password: str
) -> tuple[dict[str, Any], str]:
    session = ensure_session(session)
    if not email or not password:
        return session, "Email and password are required."
    adapter = _adapter(session)
    try:
        profile = adapter.login(email.strip(), password)
    except AuthenticationError as exc:
        return session, str(exc)
    except Exception:
        logger.exception("ui_login_failed")
        return session, "Unable to sign in. Please try again."
    session["adapter"] = adapter
    session["profile"] = profile
    session["conversation"] = []
    session["current_run"] = None
    return session, ""


def handle_register(
    session: dict[str, Any],
    full_name: str,
    email: str,
    password: str,
    confirm: str,
) -> tuple[dict[str, Any], str]:
    session = ensure_session(session)
    if not full_name or not email or not password:
        return session, "Name, email and password are required."
    if password != confirm:
        return session, "Passwords do not match."
    adapter = _adapter(session)
    try:
        adapter.register(email.strip(), password, full_name.strip())
        profile = adapter.login(email.strip(), password)
    except (RegistrationError, AuthenticationError) as exc:
        return session, str(exc)
    except Exception:
        logger.exception("ui_register_failed")
        return session, "Unable to create the account. Please try again."
    session["adapter"] = adapter
    session["profile"] = profile
    session["conversation"] = []
    session["current_run"] = None
    return session, ""


def handle_logout(session: dict[str, Any]) -> dict[str, Any]:
    session = ensure_session(session)
    adapter = session.get("adapter")
    if isinstance(adapter, GradioSessionAdapter) and adapter.is_authenticated:
        try:
            adapter.logout()
        except Exception:
            logger.info("ui_logout_revoke_failed")
    return new_session()


def handle_validate_invite(token: str) -> tuple[str, str, str]:
    """Returns (email, status_message, error)."""
    if not token or not token.strip():
        return "", "", "Paste an invitation token, or open the invitation link."
    try:
        preview = GradioSessionAdapter().preview_invitation(token.strip())
    except InvitationError as exc:
        return "", "", str(exc)
    except Exception:
        logger.exception("ui_invite_validate_failed")
        return "", "", "Unable to validate this invitation."
    return preview.email, f"Invitation for {preview.email} is {preview.status}.", ""


def handle_accept_invite(
    session: dict[str, Any],
    token: str,
    full_name: str,
    email: str,
    password: str,
    confirm: str,
) -> tuple[dict[str, Any], str]:
    session = ensure_session(session)
    if not token or not full_name or not email or not password:
        return session, "All invitation fields are required."
    if password != confirm:
        return session, "Passwords do not match."
    adapter = _adapter(session)
    try:
        profile = adapter.accept_invitation(
            token.strip(), email.strip(), password, full_name.strip()
        )
    except (InvitationError, RegistrationError, AuthenticationError) as exc:
        return session, str(exc)
    except Exception:
        logger.exception("ui_invite_accept_failed")
        return session, "Unable to activate this invitation."
    session["adapter"] = adapter
    session["profile"] = profile
    session["conversation"] = []
    session["current_run"] = None
    return session, ""


def handle_submit(
    session: dict[str, Any], message: str
) -> tuple[dict[str, Any], str, str]:
    """Submit a coding request.

    Returns (session, kind, error) where kind is ok | session_expired | quota |
    validation | error.
    """
    session = ensure_session(session)
    if not is_authenticated(session):
        return session, "session_expired", "Your session has expired. Please sign in again."
    text = (message or "").strip()
    if not text:
        return session, "validation", "Enter a coding request first."

    adapter: GradioSessionAdapter = session["adapter"]
    try:
        run = adapter.submit_request(text)
    except AuthenticationError:
        cleared = new_session()
        return cleared, "session_expired", "Your session has expired. Please sign in again."
    except QuotaExceededError as exc:
        return session, "quota", str(exc)
    except ValueError as exc:
        return session, "validation", str(exc)
    except Exception:
        logger.exception("ui_submit_failed")
        return session, "error", "CodeForge could not complete this request. Please try again."

    conversation = list(session.get("conversation") or [])
    conversation.append({"role": "user", "content": run.sanitised_request})
    from codeforge.ui.formatters import assistant_message

    conversation.append({"role": "assistant", "content": assistant_message(run)})
    session["conversation"] = conversation
    session["current_run"] = run
    try:
        session["profile"] = adapter.profile()
    except AuthenticationError:
        pass
    return session, "ok", ""


def handle_history(session: dict[str, Any]) -> list[RunRecord]:
    session = ensure_session(session)
    if not is_authenticated(session):
        return []
    try:
        return session["adapter"].my_runs()
    except AuthenticationError:
        return []
    except Exception:
        logger.exception("ui_history_failed")
        return []


def handle_quota(session: dict[str, Any]) -> QuotaStatus | None:
    session = ensure_session(session)
    if not is_authenticated(session):
        return None
    try:
        return session["adapter"].my_quota()
    except AuthenticationError:
        return None
    except Exception:
        logger.exception("ui_quota_failed")
        return None


def handle_load_run(
    session: dict[str, Any], run_id: str
) -> tuple[dict[str, Any], str]:
    session = ensure_session(session)
    if not is_authenticated(session):
        return session, "Your session has expired. Please sign in again."
    if not run_id:
        return session, ""
    try:
        run = session["adapter"].get_run(run_id)
    except AuthenticationError:
        return new_session(), "Your session has expired. Please sign in again."
    except RunNotFoundError:
        return session, "Run not found"
    except Exception:
        logger.exception("ui_load_run_failed")
        return session, "Unable to load that run."

    from codeforge.ui.formatters import assistant_message

    session["current_run"] = run
    session["conversation"] = [
        {"role": "user", "content": run.sanitised_request},
        {"role": "assistant", "content": assistant_message(run)},
    ]
    return session, ""


def handle_new_chat(session: dict[str, Any]) -> dict[str, Any]:
    session = ensure_session(session)
    session["conversation"] = []
    session["current_run"] = None
    return session


def current_profile(session: dict[str, Any]) -> UserProfile | None:
    profile = session.get("profile")
    return profile if isinstance(profile, UserProfile) else None


def current_run(session: dict[str, Any]) -> RunRecord | None:
    run = session.get("current_run")
    return run if isinstance(run, RunRecord) else None


def write_download(content: str | None, suffix: str) -> str | None:
    """Write content to a unique temp file with a safe, non-user-controlled name."""
    if not content:
        return None
    name = f"codeforge_{uuid4().hex[:10]}{suffix}"
    path = Path(tempfile.gettempdir()) / name
    path.write_text(content, encoding="utf-8")
    return str(path)


def download_code(run: RunRecord | None) -> str | None:
    if run is None or not run.generated_code:
        return None
    return write_download(run.generated_code, "_solution.py")


def download_tests(run: RunRecord | None) -> str | None:
    if run is None or not run.generated_tests:
        return None
    return write_download(run.generated_tests, "_test_solution.py")


def download_execution_report(run: RunRecord | None) -> str | None:
    if run is None:
        return None
    payload = json.dumps(execution_report_json(run), indent=2)
    return write_download(payload, "_execution.json")


def instructor_sql_notice() -> str:
    return (
        "**Ticket investigation**\n\n"
        "Questions run against the ticket selected below. "
        "The server checks the assignment on every question. "
        "Changing the ticket reference cannot open another instructor's ticket, "
        "and this screen never shows a student's name, email, or credentials.\n\n"
        "Open tickets are loaded from the handoff table. "
        "Automatic escalation is not implemented, so an empty list means "
        "nothing is assigned to you. An instructor login does not open every student."
    )


def _sql_error(exc: Exception) -> str:
    if isinstance(exc, (AuthorizationError, AuthenticationError, SqlAgentDisabledError, SqlTicketNotFoundError)):
        return str(exc)
    return "The query could not be completed."


def handle_student_sql(session: dict[str, Any], question: str) -> str:
    """Student self-service. There is no user-id field to switch."""
    session = ensure_session(session)
    if not is_authenticated(session):
        return "Sign in to ask about your own history."
    if not question or not question.strip():
        return "Enter a question about your own prompts, code, or execution results."
    try:
        answer = _adapter(session).ask_sql(question.strip(), None)
    except Exception as exc:  # noqa: BLE001 - the UI gets a safe sentence
        return _sql_error(exc)
    return sql_result_markdown(answer.message, answer.columns, answer.rows)


def handle_refresh_tickets(session: dict[str, Any]) -> str:
    session = ensure_session(session)
    if not is_authenticated(session):
        return "Sign in to view assigned tickets."
    try:
        overview = _adapter(session).sql_tickets()
    except Exception as exc:  # noqa: BLE001
        return tickets_markdown(None, error=_sql_error(exc))
    return tickets_markdown(overview)


def handle_open_ticket(session: dict[str, Any], ticket_id: str) -> str:
    session = ensure_session(session)
    if not is_authenticated(session):
        return "Sign in to open a ticket."
    if not ticket_id or not ticket_id.strip():
        return "Choose a ticket reference. The server will check that it is assigned to you."
    try:
        payload = _adapter(session).sql_ticket(ticket_id.strip())
    except Exception as exc:  # noqa: BLE001
        return ticket_context_markdown(None, error=_sql_error(exc))
    return ticket_context_markdown(payload)


def handle_instructor_sql(session: dict[str, Any], ticket_id: str, question: str) -> str:
    """Ticket question. A forged local role does not choose the principal."""
    session = ensure_session(session)
    if not is_authenticated(session):
        return "Sign in to investigate a ticket."
    if not question or not question.strip():
        return "Enter a question about the assigned ticket."
    try:
        answer = _adapter(session).ask_sql(question.strip(), (ticket_id or "").strip() or None)
    except Exception as exc:  # noqa: BLE001
        return _sql_error(exc)
    rendered = sql_result_markdown(answer.message, answer.columns, answer.rows)
    if answer.validated_sql and answer.access_mode == "instructor_ticket":
        rendered += f"\n\nValidated query:\n\n```sql\n{answer.validated_sql}\n```"
    return rendered


def pending_approvals_markdown(rows: list[dict] | None, error: str = "") -> str:
    if error:
        return f"**Approvals:** {error}"
    if not rows:
        return "_No pending approvals._"
    lines = ["### Pending approvals", ""]
    for row in rows:
        ops = ", ".join(row.get("operations") or []) or "unspecified"
        reasons = "; ".join(row.get("reasons") or []) or "unspecified"
        lines.append(
            f"- `{row.get('id')}` · {row.get('owner_name')} · {ops}\n"
            f"  {reasons}\n"
            f"  _{row.get('summary', '')[:180]}_"
        )
    lines.append("")
    lines.append("Paste an id below and confirm before approving or rejecting.")
    return "\n".join(lines)


def handle_refresh_approvals(session: dict[str, Any]) -> str:
    session = ensure_session(session)
    profile = current_profile(session)
    if profile is None or profile.role != "instructor":
        return ""
    try:
        rows = _adapter(session).pending_approvals()
    except Exception as exc:  # noqa: BLE001 - surface a short UI error
        return pending_approvals_markdown(None, error=str(exc))
    return pending_approvals_markdown(rows)


def handle_decide_approval(
    session: dict[str, Any], approval_id: str, decision: str, confirmed: bool
) -> str:
    session = ensure_session(session)
    profile = current_profile(session)
    if profile is None or profile.role != "instructor":
        return "Only instructors can decide approvals."
    if not confirmed:
        return "Confirmation is required before a decision."
    if not approval_id or not approval_id.strip():
        return "Enter an approval id."
    try:
        result = _adapter(session).decide_approval(approval_id.strip(), decision)
    except Exception as exc:  # noqa: BLE001
        return f"Decision was not applied: {exc}"
    return (
        f"Decision recorded: **{result.get('status')}** for `{result.get('id')}`.\n\n"
        + handle_refresh_approvals(session)
    )


def handle_feedback(session: dict[str, Any], vote: str, explanation: str) -> str:
    """Record thumbs feedback for the current run. Students have no approve control here."""
    session = ensure_session(session)
    run = current_run(session)
    if not is_authenticated(session):
        return "Sign in before sending feedback."
    if run is None:
        return "Submit a run before sending feedback."
    try:
        record = _adapter(session).submit_feedback(run.id, vote, explanation or "")
    except Exception as exc:  # noqa: BLE001
        return f"Feedback was not saved: {exc}"
    return f"Recorded **{record['vote']}** for run `{record['run_id']}`."
