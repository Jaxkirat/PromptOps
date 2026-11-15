"""Role-based authorization tests."""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from codeforge.api.dependencies import get_current_principal, require_instructor, require_student
from codeforge.auth.identity import AuthenticatedPrincipal
from tests.conftest import auth_header, register_and_login


def _app_with_role_routes():
    """Minimal app exposing role-guarded routes for dependency testing."""
    from codeforge.api.main import create_application

    app = create_application()

    @app.get("/role-test/student-only")
    async def student_only(
        principal: AuthenticatedPrincipal = Depends(require_student),
    ) -> dict:
        return {"user_id": principal.user_id, "role": principal.role}

    @app.get("/role-test/instructor-only")
    async def instructor_only(
        principal: AuthenticatedPrincipal = Depends(require_instructor),
    ) -> dict:
        return {"user_id": principal.user_id, "role": principal.role}

    return app


class TestRoleDependencies:
    def test_student_passes_student_gate_but_not_instructor_gate(
        self, api_env, fake_pipeline
    ) -> None:
        with TestClient(_app_with_role_routes()) as client:
            token = register_and_login(client, "roles-student@example.com")
            ok = client.get("/role-test/student-only", headers=auth_header(token))
            assert ok.status_code == 200
            assert ok.json()["role"] == "student"

            forbidden = client.get("/role-test/instructor-only", headers=auth_header(token))
            assert forbidden.status_code == 403

    def test_instructor_passes_instructor_gate(self, api_env, fake_pipeline) -> None:
        from codeforge.services.auth_service import provision_instructor

        provision_instructor("prof2@example.com", "StrongPassword123", "Professor")
        with TestClient(_app_with_role_routes()) as client:
            login = client.post(
                "/api/v1/auth/login",
                json={"email": "prof2@example.com", "password": "StrongPassword123"},
            )
            token = login.json()["access_token"]
            ok = client.get("/role-test/instructor-only", headers=auth_header(token))
            assert ok.status_code == 200
            assert ok.json()["role"] == "instructor"

    def test_both_roles_can_use_run_pipeline(self, client, fake_pipeline) -> None:
        from codeforge.services.auth_service import provision_instructor

        student_token = register_and_login(client, "runner-student@example.com")
        provision_instructor("runner-prof@example.com", "StrongPassword123", "P")
        prof_token = client.post(
            "/api/v1/auth/login",
            json={"email": "runner-prof@example.com", "password": "StrongPassword123"},
        ).json()["access_token"]

        for token in (student_token, prof_token):
            response = client.post(
                "/api/v1/runs", json={"request": "sum a list"}, headers=auth_header(token)
            )
            assert response.status_code == 201
