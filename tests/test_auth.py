"""Authentication tests: registration, login, tokens, logout."""

from __future__ import annotations

from tests.conftest import auth_header, register_and_login


class TestRegistration:
    def test_student_registration(self, client) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "student@example.com",
                "password": "StrongPassword123",
                "full_name": "Student Name",
            },
        )
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "student@example.com"
        assert body["role"] == "student"
        assert body["is_active"] is True
        assert "password" not in body and "password_hash" not in body

    def test_duplicate_registration(self, client) -> None:
        payload = {
            "email": "dup@example.com",
            "password": "StrongPassword123",
            "full_name": "Dup",
        }
        assert client.post("/api/v1/auth/register", json=payload).status_code == 201
        response = client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 400
        assert "already exists" in response.json()["detail"]

    def test_invalid_email(self, client) -> None:
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-email", "password": "StrongPassword123", "full_name": "X"},
        )
        assert response.status_code == 422

    def test_weak_password(self, client) -> None:
        for weak in ("short1", "onlyletters", "12345678"):
            response = client.post(
                "/api/v1/auth/register",
                json={"email": f"weak-{weak}@example.com", "password": weak, "full_name": "X"},
            )
            assert response.status_code == 400, weak
            assert "Password" in response.json()["detail"]


class TestLogin:
    def test_login_returns_token_and_profile(self, client) -> None:
        client.post(
            "/api/v1/auth/register",
            json={"email": "login@example.com", "password": "StrongPassword123", "full_name": "L"},
        )
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "login@example.com", "password": "StrongPassword123"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 30 * 60
        assert body["access_token"]
        assert body["user"]["email"] == "login@example.com"
        assert body["user"]["role"] == "student"

    def test_incorrect_password(self, client) -> None:
        client.post(
            "/api/v1/auth/register",
            json={"email": "wrong@example.com", "password": "StrongPassword123", "full_name": "W"},
        )
        response = client.post(
            "/api/v1/auth/login",
            json={"email": "wrong@example.com", "password": "WrongPassword123"},
        )
        assert response.status_code == 401

    def test_unknown_email_same_error_as_wrong_password(self, client) -> None:
        client.post(
            "/api/v1/auth/register",
            json={"email": "known@example.com", "password": "StrongPassword123", "full_name": "K"},
        )
        wrong_pw = client.post(
            "/api/v1/auth/login",
            json={"email": "known@example.com", "password": "WrongPassword999"},
        )
        unknown = client.post(
            "/api/v1/auth/login",
            json={"email": "ghost@example.com", "password": "StrongPassword123"},
        )
        assert wrong_pw.status_code == unknown.status_code == 401
        assert wrong_pw.json() == unknown.json()


class TestTokens:
    def test_missing_token(self, client) -> None:
        assert client.get("/api/v1/auth/me").status_code == 401

    def test_invalid_token(self, client) -> None:
        response = client.get("/api/v1/auth/me", headers=auth_header("garbage.token.here"))
        assert response.status_code == 401

    def test_expired_token(self, client) -> None:
        from codeforge.auth.jwt_handler import create_access_token
        from codeforge.database.database import session_scope
        from codeforge.database.repositories import user_repository

        register_and_login(client, "expired@example.com")
        with session_scope() as db:
            user = user_repository.get_by_email(db, "expired@example.com")
            user_id = user.id
        token, _, _ = create_access_token(user_id, expires_minutes=-1)
        response = client.get("/api/v1/auth/me", headers=auth_header(token))
        assert response.status_code == 401
        assert "expired" in response.json()["detail"].lower()

    def test_inactive_user(self, client) -> None:
        from codeforge.database.database import session_scope
        from codeforge.database.repositories import user_repository

        token = register_and_login(client, "inactive@example.com")
        with session_scope() as db:
            user = user_repository.get_by_email(db, "inactive@example.com")
            user.is_active = False
            db.add(user)
        response = client.get("/api/v1/auth/me", headers=auth_header(token))
        assert response.status_code == 401
        assert "inactive" in response.json()["detail"].lower()


class TestLogout:
    def test_logout_revokes_token(self, client) -> None:
        token = register_and_login(client, "logout@example.com")
        assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 200

        response = client.post("/api/v1/auth/logout", headers=auth_header(token))
        assert response.status_code == 200

        # The same token is now rejected everywhere.
        assert client.get("/api/v1/auth/me", headers=auth_header(token)).status_code == 401
        assert client.get("/api/v1/runs", headers=auth_header(token)).status_code == 401

    def test_me_endpoint(self, client) -> None:
        token = register_and_login(client, "me@example.com")
        response = client.get("/api/v1/auth/me", headers=auth_header(token))
        assert response.status_code == 200
        assert response.json()["email"] == "me@example.com"
