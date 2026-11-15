"""End-to-end API integration tests and secure-logging verification."""

from __future__ import annotations

import logging

from tests.conftest import auth_header, register_and_login

SYNTHETIC_KEY = "sk-SyntheticTestSecret1234567890"
SYNTHETIC_EMAIL = "victim.person@secretcorp.com"


class TestFullApiFlow:
    def test_register_login_submit_history_quota(self, client, fake_pipeline) -> None:
        token = register_and_login(client, "flow@example.com")

        # Submit a run.
        created = client.post(
            "/api/v1/runs",
            json={"request": "Write a palindrome checker"},
            headers=auth_header(token),
        )
        assert created.status_code == 201
        run = created.json()
        assert run["status"] == "success"
        assert run["task_type"] == "python"
        assert run["test_results"]["passed"] == 3
        assert run["generated_code"]

        # History contains it and ownership is enforced via the token.
        history = client.get("/api/v1/runs", headers=auth_header(token)).json()
        assert history["total"] == 1
        assert history["runs"][0]["id"] == run["id"]

        # Single-run retrieval.
        single = client.get(f"/api/v1/runs/{run['id']}", headers=auth_header(token))
        assert single.status_code == 200

        # Quota reflects the run.
        quota = client.get("/api/v1/users/me/quota", headers=auth_header(token)).json()
        assert quota["used"] == 1

        # Profile endpoints.
        assert client.get("/api/v1/users/me", headers=auth_header(token)).json()[
            "email"
        ] == "flow@example.com"

    def test_swagger_docs_available(self, client) -> None:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200

    def test_runs_require_authentication(self, client) -> None:
        assert client.post("/api/v1/runs", json={"request": "x"}).status_code == 401
        assert client.get("/api/v1/runs").status_code == 401

    def test_empty_request_rejected_without_quota_use(self, client, fake_pipeline) -> None:
        token = register_and_login(client, "empty@example.com")
        response = client.post(
            "/api/v1/runs", json={"request": "   "}, headers=auth_header(token)
        )
        assert response.status_code == 422
        quota = client.get("/api/v1/users/me/quota", headers=auth_header(token)).json()
        assert quota["used"] == 0


class TestPrivacyAtIngestion:
    def test_llm_receives_masked_text_and_db_stores_no_secrets(
        self, client, fake_pipeline
    ) -> None:
        """DEMO 3/4: raw secrets never reach the pipeline or the database."""
        token = register_and_login(client, "privacy@example.com")
        request_text = (
            f"My key is {SYNTHETIC_KEY}, mail {SYNTHETIC_EMAIL}, phone +91 9876543210, "
            "aadhaar 2345 6789 0123, card 4111 1111 1111 1111 — write a sum function"
        )
        response = client.post(
            "/api/v1/runs", json={"request": request_text}, headers=auth_header(token)
        )
        assert response.status_code == 201
        body = response.json()

        # What the pipeline (and therefore the LLM) received was sanitized.
        assert len(fake_pipeline.calls) == 1
        pipeline_input = fake_pipeline.calls[0]
        assert "[SECRET]" in pipeline_input
        for raw in (SYNTHETIC_KEY, SYNTHETIC_EMAIL, "9876543210", "2345 6789 0123", "4111"):
            assert raw not in pipeline_input

        # The API response and persisted run contain no raw values.
        assert body["redaction_count"] == 5
        assert SYNTHETIC_KEY not in body["sanitised_request"]

        from codeforge.database.database import session_scope
        from codeforge.database.models import Run

        with session_scope() as db:
            stored = db.query(Run).filter(Run.id == body["id"]).one()
            assert SYNTHETIC_KEY not in stored.sanitised_request
            assert SYNTHETIC_EMAIL not in stored.sanitised_request
            assert "[SECRET]" in stored.sanitised_request


class TestSecureLogging:
    def test_synthetic_secrets_never_appear_in_logs(self, client, fake_pipeline, caplog) -> None:
        password = "StrongPassword123"
        with caplog.at_level(logging.DEBUG):
            token = register_and_login(client, "logcheck@example.com", password)
            client.post(
                "/api/v1/runs",
                json={"request": f"use my key {SYNTHETIC_KEY} and email {SYNTHETIC_EMAIL}"},
                headers=auth_header(token),
            )
            client.post("/api/v1/auth/logout", headers=auth_header(token))

        logged = caplog.text
        assert SYNTHETIC_KEY not in logged
        assert SYNTHETIC_EMAIL not in logged
        assert password not in logged
        assert token not in logged  # JWT never logged

    def test_log_contains_only_permitted_metadata(self, client, fake_pipeline, caplog) -> None:
        with caplog.at_level(logging.INFO, logger="codeforge"):
            token = register_and_login(client, "logmeta@example.com")
            client.post(
                "/api/v1/runs",
                json={"request": f"key {SYNTHETIC_KEY} task"},
                headers=auth_header(token),
            )
        run_lines = [r.getMessage() for r in caplog.records if "run_completed" in r.getMessage()]
        assert len(run_lines) == 1
        assert "redactions=1" in run_lines[0]
        assert "categories=api_key" in run_lines[0]
        assert "status=success" in run_lines[0]
