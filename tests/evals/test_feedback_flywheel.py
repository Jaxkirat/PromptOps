"""Feedback capture and the candidate golden-case workflow."""

import json

import pytest

from codeforge.auth.identity import AuthenticatedPrincipal, principal_context
from codeforge.evals.feedback_to_golden import feedback_to_case, write_pending
from codeforge.evals.flywheel_subject import classify_label, classify_label_fixed
from codeforge.exceptions import FeedbackConflictError, RunNotFoundError
from codeforge.services.feedback_service import submit_feedback
from tests.conftest import auth_header, register_and_login


def test_student_feedback_is_masked_and_isolated(client, tmp_path):
    owner = register_and_login(client, "feedback-owner@example.com")
    other = register_and_login(client, "feedback-other@example.com")
    created = client.post(
        "/api/v1/runs",
        json={"request": "Write a function that returns 1"},
        headers=auth_header(owner),
    )
    assert created.status_code == 201, created.text
    run_id = created.json()["id"]
    recorded = client.post(
        f"/api/v1/runs/{run_id}/feedback",
        json={"vote": "down", "explanation": "key sk-synthetickey123456 leaked"},
        headers=auth_header(owner),
    )
    assert recorded.status_code == 201, recorded.text
    body = recorded.json()
    assert "sk-synthetickey123456" not in body["explanation"]
    assert "[SECRET]" in body["explanation"]
    assert body["vote"] == "down"

    foreign = client.post(
        f"/api/v1/runs/{run_id}/feedback",
        json={"vote": "down"},
        headers=auth_header(other),
    )
    assert foreign.status_code == 404

    duplicate = client.post(
        f"/api/v1/runs/{run_id}/feedback",
        json={"vote": "up"},
        headers=auth_header(owner),
    )
    assert duplicate.status_code == 409

    me = client.get("/api/v1/users/me", headers=auth_header(owner)).json()
    with principal_context(
        AuthenticatedPrincipal(user_id=me["id"], role="student", email=me["email"], is_active=True)
    ):
        with pytest.raises(FeedbackConflictError):
            submit_feedback(run_id, "down", "again")

    case = feedback_to_case(
        body["id"],
        expected={"label": "python"},
        case_input={"text": "Write a Python function that builds a query string"},
        description="Python function requests that mention a query stay Python",
    )
    path = write_pending(case, tmp_path)
    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["expected"] == {"label": "python"}
    assert "sk-" not in json.dumps(saved)
    assert classify_label(saved["input"]["text"]) == "sql"
    assert classify_label_fixed(saved["input"]["text"]) == "python"


def test_missing_feedback_is_not_found(api_env):
    from codeforge.services.auth_service import register_student

    user = register_student("missing-feedback@example.com", "StrongPassword123", "Missing")
    with principal_context(
        AuthenticatedPrincipal(user_id=user.id, role="student", email=user.email, is_active=True)
    ):
        with pytest.raises(RunNotFoundError):
            from codeforge.services.feedback_service import get_feedback

            get_feedback("does-not-exist")
