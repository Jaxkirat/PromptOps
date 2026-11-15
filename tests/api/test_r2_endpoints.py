"""R2 HTTP endpoints: ownership, instructor authority, and no self-approval."""

from codeforge.services.approval_service import create_approval
from codeforge.services.invitation_service import create_instructor_invitation
from tests.conftest import auth_header, register_and_login


def _instructor_token(client) -> str:
    created = create_instructor_invitation("r2-prof@example.com")
    token = created.invite_url.split("token=", 1)[1]
    accepted = client.post(
        "/api/v1/auth/invitations/accept",
        json={
            "token": token,
            "email": "r2-prof@example.com",
            "password": "StrongPassword123",
            "full_name": "Prof",
        },
    )
    assert accepted.status_code == 201, accepted.text
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "r2-prof@example.com", "password": "StrongPassword123"},
    )
    assert login.status_code == 200, login.text
    return login.json()["access_token"]


def test_student_cannot_list_or_approve(client, monkeypatch):
    student = register_and_login(client, "r2-student@example.com")
    other = register_and_login(client, "r2-other@example.com")
    instructor = _instructor_token(client)
    me = client.get("/api/v1/users/me", headers=auth_header(student)).json()
    approval_id = create_approval(
        user_id=me["id"],
        run_id=None,
        thread_id="t",
        reasons=["socket"],
        operations=["socket"],
        code_text="import socket\n",
        tests_text="def test_x():\n    assert True\n",
        summary="network",
    )
    monkeypatch.setattr(
        "codeforge.services.approval_service.resume_graph",
        lambda thread_id, resume: {"report": None},
    )

    pending = client.get("/api/v1/approvals/pending", headers=auth_header(student))
    assert pending.status_code == 403

    foreign = client.get(f"/api/v1/approvals/{approval_id}", headers=auth_header(other))
    assert foreign.status_code == 404

    own = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers=auth_header(student),
        json={"confirm": True},
    )
    assert own.status_code == 403

    unconfirmed = client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        headers=auth_header(instructor),
        json={"confirm": False},
    )
    assert unconfirmed.status_code == 422

    rejected = client.post(
        f"/api/v1/approvals/{approval_id}/reject",
        headers=auth_header(instructor),
        json={"confirm": True},
    )
    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"

    again = client.post(
        f"/api/v1/approvals/{approval_id}/approve",
        headers=auth_header(instructor),
        json={"confirm": True},
    )
    assert again.status_code == 409


def test_missing_run_execution_is_404(client):
    token = register_and_login(client, "r2-exec@example.com")
    response = client.get("/api/v1/runs/does-not-exist/execution", headers=auth_header(token))
    assert response.status_code == 404
