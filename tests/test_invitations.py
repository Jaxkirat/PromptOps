"""Instructor invitation tests — generation, validation, acceptance, reuse."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from codeforge.database.database import session_scope
from codeforge.database.models import InstructorInvitation
from codeforge.database.repositories import invitation_repository
from codeforge.exceptions import InvitationError
from codeforge.services.invitation_service import (
    accept_invitation,
    create_instructor_invitation,
    hash_invitation_token,
    validate_invitation,
)
from tests.conftest import auth_header, register_and_login


def _raw_token_from_url(url: str) -> str:
    return url.split("token=", 1)[1]


class TestInvitationLifecycle:
    def test_valid_invitation_creates_instructor(self, api_env) -> None:
        created = create_instructor_invitation("prof@example.com")
        token = _raw_token_from_url(created.invite_url)
        preview = validate_invitation(token)
        assert preview.email == "prof@example.com"
        assert preview.status == "valid"

        user = accept_invitation(token, "prof@example.com", "StrongPassword123", "Professor")
        assert user.role == "instructor"
        assert user.email == "prof@example.com"

    def test_invalid_token(self, api_env) -> None:
        import pytest

        with pytest.raises(InvitationError, match="Invalid"):
            validate_invitation("not-a-real-token")

    def test_expired_invitation(self, api_env) -> None:
        import pytest

        created = create_instructor_invitation("old@example.com")
        token = _raw_token_from_url(created.invite_url)
        with session_scope() as db:
            row = invitation_repository.get_by_token_hash(db, hash_invitation_token(token))
            assert row is not None
            row.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        with pytest.raises(InvitationError, match="expired"):
            validate_invitation(token)

    def test_reused_invitation(self, api_env) -> None:
        import pytest

        created = create_instructor_invitation("once@example.com")
        token = _raw_token_from_url(created.invite_url)
        accept_invitation(token, "once@example.com", "StrongPassword123", "Once")
        with pytest.raises(InvitationError, match="already been used"):
            accept_invitation(token, "once@example.com", "StrongPassword123", "Once")

    def test_wrong_intended_email(self, api_env) -> None:
        import pytest

        created = create_instructor_invitation("locked@example.com")
        token = _raw_token_from_url(created.invite_url)
        with pytest.raises(InvitationError, match="different email"):
            accept_invitation(token, "other@example.com", "StrongPassword123", "Other")

    def test_plaintext_token_is_not_stored(self, api_env) -> None:
        created = create_instructor_invitation("hashcheck@example.com")
        token = _raw_token_from_url(created.invite_url)
        with session_scope() as db:
            rows = db.query(InstructorInvitation).all()
            assert rows
            dumped = " ".join(row.token_hash for row in rows)
            assert token not in dumped
            assert hash_invitation_token(token) in dumped

    def test_cannot_create_multiple_instructors_from_one_invite(self, api_env) -> None:
        import pytest

        created = create_instructor_invitation("single@example.com")
        token = _raw_token_from_url(created.invite_url)
        accept_invitation(token, "single@example.com", "StrongPassword123", "One")
        with pytest.raises(InvitationError):
            accept_invitation(token, "single@example.com", "StrongPassword123", "Two")


class TestInvitationApi:
    def test_validate_and_accept_endpoints(self, client) -> None:
        created = create_instructor_invitation("api-prof@example.com")
        token = _raw_token_from_url(created.invite_url)

        preview = client.post("/api/v1/auth/invitations/validate", json={"token": token})
        assert preview.status_code == 200
        assert preview.json()["email"] == "api-prof@example.com"

        accepted = client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "token": token,
                "email": "api-prof@example.com",
                "password": "StrongPassword123",
                "full_name": "API Professor",
            },
        )
        assert accepted.status_code == 201
        assert accepted.json()["role"] == "instructor"

        login = client.post(
            "/api/v1/auth/login",
            json={"email": "api-prof@example.com", "password": "StrongPassword123"},
        )
        assert login.status_code == 200
        assert login.json()["user"]["role"] == "instructor"

    def test_student_cannot_create_invitation(self, client) -> None:
        token = register_and_login(client, "no-invite@example.com")
        response = client.post(
            "/api/v1/auth/invitations",
            json={"email": "someone@example.com"},
            headers=auth_header(token),
        )
        assert response.status_code in (404, 405, 422)

    def test_public_register_still_cannot_be_instructor(self, client) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "still-student@example.com",
                "password": "StrongPassword123",
                "full_name": "Nope",
                "role": "instructor",
            },
        )
        assert response.status_code == 201
        assert response.json()["role"] == "student"

    def test_cli_prints_url_once(self, api_env, capsys) -> None:
        from codeforge.cli import main

        assert main(["create-instructor-invite", "--email", "cli-prof@example.com"]) == 0
        output = capsys.readouterr().out
        assert "/ui/?token=" in output
        assert "cli-prof@example.com" in output

    def test_role_assigned_by_backend_not_payload(self, client) -> None:
        created = create_instructor_invitation("role-src@example.com")
        token = _raw_token_from_url(created.invite_url)
        response = client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "token": token,
                "email": "role-src@example.com",
                "password": "StrongPassword123",
                "full_name": "Role Source",
                "role": "student",
            },
        )
        assert response.status_code == 201
        assert response.json()["role"] == "instructor"
