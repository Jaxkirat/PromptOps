"""Isolated database and API harness for golden cases."""

from __future__ import annotations

import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from codeforge.evals.fakes import RecordingPipeline
from codeforge.models.schemas import ExecutionResult


class EvalHarness:
    def __init__(self) -> None:
        self._tmp: tempfile.TemporaryDirectory[str] | None = None
        self._saved_env: dict[str, str | None] = {}
        self.pipeline = RecordingPipeline()
        self.client = None
        self.root: Path | None = None

    def __enter__(self) -> "EvalHarness":
        self._tmp = tempfile.TemporaryDirectory(prefix="codeforge_eval_")
        self.root = Path(self._tmp.name)
        db_path = self.root / "eval.sqlite"
        keys = {
            "DATABASE_URL": f"sqlite:///{db_path.as_posix()}",
            "JWT_SECRET_KEY": "eval-gate-secret-not-production-0123456789abcd",
            "JWT_ALGORITHM": "HS256",
            "ACCESS_TOKEN_EXPIRE_MINUTES": "30",
            "MAX_RUNS_PER_USER_PER_DAY": "50",
            "INITIAL_INSTRUCTOR_EMAIL": "",
            "INITIAL_INSTRUCTOR_PASSWORD": "",
            "CODEFORGE_SANDBOX_BACKEND": "restricted-process",
            "CODEFORGE_CHECKPOINT_PATH": str(self.root / "checkpoints.sqlite"),
            "CODEFORGE_SANDBOX_TIMEOUT_SECONDS": "5",
        }
        self._saved_env = {key: os.environ.get(key) for key in keys}
        os.environ.update(keys)
        from codeforge.config.settings import get_settings
        from codeforge.database.database import init_db, reset_database_state
        from codeforge.graph import workflow as workflow_module
        from codeforge.services.run_service import set_pipeline_runner

        get_settings.cache_clear()
        workflow_module._checkpointer = None
        workflow_module._checkpointer_path = None
        reset_database_state()
        init_db()
        set_pipeline_runner(self.pipeline)
        from fastapi.testclient import TestClient

        from codeforge.api.main import create_application

        self.client = TestClient(create_application())
        self.client.__enter__()
        import codeforge.services.approval_service as approval_service

        self._original_resume = approval_service.resume_graph
        approval_service.resume_graph = lambda thread_id, resume: {"report": None}
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        import codeforge.services.approval_service as approval_service
        from codeforge.config.settings import get_settings
        from codeforge.database.database import reset_database_state
        from codeforge.graph import workflow as workflow_module
        from codeforge.services.run_service import set_pipeline_runner

        approval_service.resume_graph = self._original_resume
        from codeforge.sql_agent.proposer import set_sql_proposer
        from codeforge.sql_agent.tickets import set_ticket_access

        set_sql_proposer(None)
        set_ticket_access(None)
        set_pipeline_runner(None)
        if self.client is not None:
            self.client.__exit__(exc_type, exc, tb)
        reset_database_state()
        get_settings.cache_clear()
        if workflow_module._checkpointer is not None:
            workflow_module._checkpointer.conn.close()
        workflow_module._checkpointer = None
        workflow_module._checkpointer_path = None
        for key, value in self._saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        get_settings.cache_clear()
        if self._tmp is not None:
            self._tmp.cleanup()

    def email(self, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:8]}@example.com"

    def register_student(self, prefix: str = "student") -> tuple[str, str]:
        email = self.email(prefix)
        created = self.client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "StrongPassword123", "full_name": "Eval Student", "role": "instructor"},
        )
        if created.status_code != 201:
            raise AssertionError(created.text)
        return self._login(email)

    def register_instructor(self, prefix: str = "instructor") -> tuple[str, str]:
        from codeforge.services.invitation_service import create_instructor_invitation

        email = self.email(prefix)
        created = create_instructor_invitation(email)
        token = created.invite_url.split("token=", 1)[1]
        accepted = self.client.post(
            "/api/v1/auth/invitations/accept",
            json={
                "token": token,
                "email": email,
                "password": "StrongPassword123",
                "full_name": "Eval Instructor",
            },
        )
        if accepted.status_code != 201:
            raise AssertionError(accepted.text)
        return self._login(email)

    def _login(self, email: str) -> tuple[str, str]:
        response = self.client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "StrongPassword123"},
        )
        if response.status_code != 200:
            raise AssertionError(response.text)
        body = response.json()
        return body["access_token"], body["user"]["id"]

    def headers(self, token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def submit(self, token: str, text: str) -> dict:
        self.pipeline.calls.clear()
        response = self.client.post(
            "/api/v1/runs",
            json={"request": text},
            headers=self.headers(token),
        )
        if response.status_code != 201:
            raise AssertionError(response.text)
        return response.json()

    @contextmanager
    def capture_logs(self) -> Iterator[logging.Handler]:
        stream: list[str] = []

        class _ListHandler(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                stream.append(record.getMessage())

        handler = _ListHandler()
        logger = logging.getLogger("codeforge")
        logger.addHandler(handler)
        try:
            yield handler
            handler.messages = stream  # type: ignore[attr-defined]
        finally:
            logger.removeHandler(handler)

    @contextmanager
    def sandbox_spy(self) -> Iterator[list[tuple[str, str]]]:
        import codeforge.graph.nodes as nodes

        calls: list[tuple[str, str]] = []
        original = nodes.run_sandbox

        def spy(code: str, tests: str, policy, approved: bool = False, settings=None):
            calls.append((code, tests))
            return ExecutionResult(
                status="passed",
                exit_code=0,
                executed=True,
                passed_tests=1,
                total_tests=1,
                sandbox_backend="spy",
                network_isolated=False,
                filesystem_isolated=False,
            )

        nodes.run_sandbox = spy
        try:
            yield calls
        finally:
            nodes.run_sandbox = original
