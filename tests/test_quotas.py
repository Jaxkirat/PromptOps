"""Per-user quota tests: enforcement, isolation, UTC reset, concurrency."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from codeforge.exceptions import QuotaExceededError
from tests.conftest import auth_header, register_and_login


@pytest.fixture
def small_quota(api_env, monkeypatch):
    from codeforge.config.settings import get_settings

    monkeypatch.setenv("MAX_RUNS_PER_USER_PER_DAY", "3")
    get_settings.cache_clear()
    yield 3
    get_settings.cache_clear()


class TestQuotaEnforcement:
    def test_fourth_run_returns_429_and_other_users_unaffected(
        self, small_quota, fake_pipeline
    ) -> None:
        """DEMO 5: limit 3 — user A's 4th run is rejected, user B still works."""
        from fastapi.testclient import TestClient

        from codeforge.api.main import create_application

        with TestClient(create_application()) as client:
            token_a = register_and_login(client, "quota-a@example.com")
            token_b = register_and_login(client, "quota-b@example.com")

            for i in range(3):
                response = client.post(
                    "/api/v1/runs", json={"request": f"task {i}"}, headers=auth_header(token_a)
                )
                assert response.status_code == 201

            calls_before_rejection = len(fake_pipeline.calls)
            rejected = client.post(
                "/api/v1/runs", json={"request": "task 4"}, headers=auth_header(token_a)
            )
            assert rejected.status_code == 429
            assert "quota" in rejected.json()["detail"].lower()
            # The pipeline (LangGraph) was NOT invoked for the rejected request.
            assert len(fake_pipeline.calls) == calls_before_rejection

            # Independent per-user quota: B is unaffected.
            response = client.post(
                "/api/v1/runs", json={"request": "b task"}, headers=auth_header(token_b)
            )
            assert response.status_code == 201

    def test_quota_endpoint(self, small_quota, fake_pipeline) -> None:
        from fastapi.testclient import TestClient

        from codeforge.api.main import create_application

        with TestClient(create_application()) as client:
            token = register_and_login(client, "quota-view@example.com")
            quota = client.get("/api/v1/users/me/quota", headers=auth_header(token)).json()
            assert quota == {
                "limit": 3,
                "used": 0,
                "remaining": 3,
                "utc_date": datetime.now(timezone.utc).date().isoformat(),
            }

            client.post("/api/v1/runs", json={"request": "one"}, headers=auth_header(token))
            quota = client.get("/api/v1/users/me/quota", headers=auth_header(token)).json()
            assert quota["used"] == 1 and quota["remaining"] == 2

    def test_utc_reset(self, small_quota, fake_pipeline) -> None:
        """Yesterday's exhausted quota does not affect today."""
        from codeforge.database.database import session_scope
        from codeforge.database.models import QuotaUsage, User
        from codeforge.services.quota_service import reserve_run

        with session_scope() as db:
            user = User(
                email="yesterday@example.com",
                password_hash="x",
                full_name="Y",
                role="student",
            )
            db.add(user)
            db.flush()
            user_id = user.id
            db.add(
                QuotaUsage(
                    user_id=user_id,
                    usage_date=(datetime.now(timezone.utc) - timedelta(days=1)).date(),
                    reserved_count=3,
                    quota_limit=3,
                )
            )

        # Yesterday is full, but today's reservation succeeds.
        reserve_run(user_id)

    def test_concurrent_reservations_never_exceed_limit(self, small_quota) -> None:
        from codeforge.database.database import session_scope
        from codeforge.database.models import QuotaUsage, User
        from codeforge.services.quota_service import reserve_run

        with session_scope() as db:
            user = User(
                email="concurrent@example.com",
                password_hash="x",
                full_name="C",
                role="student",
            )
            db.add(user)
            db.flush()
            user_id = user.id

        results: list[bool] = []

        def attempt() -> bool:
            try:
                reserve_run(user_id)
                return True
            except QuotaExceededError:
                return False

        with ThreadPoolExecutor(max_workers=10) as pool:
            results = [f.result() for f in [pool.submit(attempt) for _ in range(10)]]

        assert sum(results) == 3  # exactly the limit, despite 10 concurrent attempts

        with session_scope() as db:
            row = db.query(QuotaUsage).filter(QuotaUsage.user_id == user_id).one()
            assert row.reserved_count == 3
