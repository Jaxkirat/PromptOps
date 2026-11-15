"""Run ownership isolation tests — the explicit hackathon requirement."""

from __future__ import annotations

import inspect

from codeforge.services import run_service
from tests.conftest import auth_header, register_and_login


class TestFunctionSignatures:
    def test_get_my_runs_takes_no_arguments(self) -> None:
        assert list(inspect.signature(run_service.get_my_runs).parameters) == []

    def test_get_run_takes_only_run_id(self) -> None:
        assert list(inspect.signature(run_service.get_run).parameters) == ["run_id"]

    def test_no_user_id_run_fetchers_exist(self) -> None:
        for forbidden in ("get_past_runs", "get_user_runs", "fetch_runs"):
            assert not hasattr(run_service, forbidden)


class TestDatabaseIsolation:
    def test_users_see_only_their_own_runs(self, client, fake_pipeline) -> None:
        token_a = register_and_login(client, "user-a@example.com")
        token_b = register_and_login(client, "user-b@example.com")

        for i in range(3):
            response = client.post(
                "/api/v1/runs", json={"request": f"task A{i}"}, headers=auth_header(token_a)
            )
            assert response.status_code == 201
        for i in range(2):
            response = client.post(
                "/api/v1/runs", json={"request": f"task B{i}"}, headers=auth_header(token_b)
            )
            assert response.status_code == 201

        runs_a = client.get("/api/v1/runs", headers=auth_header(token_a)).json()
        runs_b = client.get("/api/v1/runs", headers=auth_header(token_b)).json()
        assert runs_a["total"] == 3
        assert runs_b["total"] == 2
        assert all("task A" in run["sanitised_request"] for run in runs_a["runs"])
        assert all("task B" in run["sanitised_request"] for run in runs_b["runs"])

    def test_cross_user_access_is_identical_404(self, client, fake_pipeline) -> None:
        """DEMO 2: foreign-owned and nonexistent runs are indistinguishable."""
        token_a = register_and_login(client, "owner@example.com")
        token_b = register_and_login(client, "intruder@example.com")

        run_id = client.post(
            "/api/v1/runs", json={"request": "my private task"}, headers=auth_header(token_a)
        ).json()["id"]

        # Owner can read it.
        assert client.get(f"/api/v1/runs/{run_id}", headers=auth_header(token_a)).status_code == 200

        foreign = client.get(f"/api/v1/runs/{run_id}", headers=auth_header(token_b))
        missing = client.get(
            "/api/v1/runs/does-not-exist-run-id", headers=auth_header(token_b)
        )

        assert foreign.status_code == 404  # never 403
        assert missing.status_code == 404
        assert foreign.json() == missing.json() == {"detail": "Run not found"}

    def test_database_query_enforces_ownership(self, client, fake_pipeline) -> None:
        """Repository-level check: get_for_owner returns None for foreign runs."""
        from codeforge.database.database import session_scope
        from codeforge.database.repositories import run_repository, user_repository

        token_a = register_and_login(client, "dbcheck-a@example.com")
        register_and_login(client, "dbcheck-b@example.com")
        run_id = client.post(
            "/api/v1/runs", json={"request": "secret work"}, headers=auth_header(token_a)
        ).json()["id"]

        with session_scope() as db:
            user_b = user_repository.get_by_email(db, "dbcheck-b@example.com")
            assert run_repository.get_for_owner(db, user_b.id, run_id) is None
            user_a = user_repository.get_by_email(db, "dbcheck-a@example.com")
            assert run_repository.get_for_owner(db, user_a.id, run_id) is not None

    def test_run_request_rejects_identity_fields(self, client, fake_pipeline) -> None:
        """user_id / role / owner_id / is_instructor / quota_override are rejected."""
        token = register_and_login(client, "strict@example.com")
        for field in ("user_id", "role", "owner_id", "is_instructor", "quota_override"):
            response = client.post(
                "/api/v1/runs",
                json={"request": "task", field: "evil-value"},
                headers=auth_header(token),
            )
            assert response.status_code == 422, field
