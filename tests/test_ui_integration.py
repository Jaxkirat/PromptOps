"""UI integration tests — handlers + adapter, no live browser."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from codeforge.models.schemas import CodeOutput, ExecutionResult, FinalReport, RouterOutput, TestOutput
from codeforge.services.invitation_service import create_instructor_invitation
from codeforge.services.run_service import set_pipeline_runner
from codeforge.ui.formatters import assistant_message, execution_markdown, requirements_markdown
from codeforge.ui.formatters import tests_summary_markdown as format_tests_summary
from codeforge.ui.handlers import (
    handle_accept_invite,
    handle_history,
    handle_load_run,
    handle_login,
    handle_logout,
    handle_new_chat,
    handle_quota,
    handle_register,
    handle_submit,
    handle_validate_invite,
    is_authenticated,
    new_session,
)
from tests.conftest import FakePipeline
from tests.test_invitations import _raw_token_from_url


class UnsupportedPipeline:
    def __init__(self, task_type: str) -> None:
        self.calls: list[str] = []
        self.task_type = task_type

    def __call__(self, text: str) -> dict:
        self.calls.append(text)
        report = FinalReport(
            user_request=text,
            status="unsupported",
            status_detail=(
                "SQL request correctly identified, but SQL execution is not implemented "
                "in Phase 1 (planned: R7 Safe SQL Agent)."
                if self.task_type == "sql"
                else "Not a coding request."
            ),
            task_type=self.task_type,
            language="sql" if self.task_type == "sql" else "none",
            router_output=RouterOutput(
                task_type=self.task_type,  # type: ignore[arg-type]
                language="sql" if self.task_type == "sql" else "none",
                description="classified",
                confidence=0.99,
                reasoning="router",
            ),
            generation_successful=False,
            execution_successful=False,
            tests_passed=False,
        )
        return {"user_request": text, "report": report}


class FailingTestsPipeline:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def __call__(self, text: str) -> dict:
        self.calls.append(text)
        report = FinalReport(
            user_request=text,
            status="tests_failed",
            status_detail="1 of 1 tests failed in actual pytest execution.",
            task_type="python",
            language="python",
            code=CodeOutput(language="python", code="def add(a, b):\n    return a - b\n"),
            tests=TestOutput(
                language="python",
                test_framework="pytest",
                test_code="from solution import add\n\ndef test_add():\n    assert add(2, 3) == 5\n",
            ),
            execution=ExecutionResult(
                status="failed",
                exit_code=1,
                total_tests=1,
                passed_tests=0,
                failed_tests=1,
                execution_time_seconds=0.2,
            ),
            generation_successful=True,
            execution_successful=True,
            tests_passed=False,
        )
        return {"user_request": text, "report": report}


class TestAuthHandlers:
    def test_student_registration_and_login(self, api_env, fake_pipeline) -> None:
        session = new_session()
        session, error = handle_register(
            session, "Ada", "ada@example.com", "StrongPassword123", "StrongPassword123"
        )
        assert error == ""
        assert is_authenticated(session)
        assert session["profile"].role == "student"

        session = handle_logout(session)
        assert not is_authenticated(session)

        session, error = handle_login(session, "ada@example.com", "StrongPassword123")
        assert error == ""
        assert session["profile"].email == "ada@example.com"

    def test_invalid_credentials(self, api_env, fake_pipeline) -> None:
        session = new_session()
        handle_register(session, "Ada", "ada2@example.com", "StrongPassword123", "StrongPassword123")
        session = handle_logout(session)
        session, error = handle_login(session, "ada2@example.com", "WrongPassword123")
        assert error
        assert not is_authenticated(session)

    def test_password_mismatch(self, api_env) -> None:
        session, error = handle_register(
            new_session(), "Ada", "ada3@example.com", "StrongPassword123", "Mismatch123"
        )
        assert "do not match" in error.lower()

    def test_expired_session_on_submit(self, api_env, fake_pipeline) -> None:
        session, kind, error = handle_submit(new_session(), "write a palindrome checker")
        assert kind == "session_expired"


class TestInvitationHandlers:
    def test_valid_activation_assigns_instructor(self, api_env, fake_pipeline) -> None:
        created = create_instructor_invitation("ui-prof@example.com")
        token = _raw_token_from_url(created.invite_url)
        email, status, error = handle_validate_invite(token)
        assert error == ""
        assert email == "ui-prof@example.com"

        session, error = handle_accept_invite(
            new_session(),
            token,
            "Professor UI",
            "ui-prof@example.com",
            "StrongPassword123",
            "StrongPassword123",
        )
        assert error == ""
        assert session["profile"].role == "instructor"

    def test_reused_invitation_handler(self, api_env, fake_pipeline) -> None:
        created = create_instructor_invitation("ui-once@example.com")
        token = _raw_token_from_url(created.invite_url)
        handle_accept_invite(
            new_session(),
            token,
            "P",
            "ui-once@example.com",
            "StrongPassword123",
            "StrongPassword123",
        )
        session, error = handle_accept_invite(
            new_session(),
            token,
            "P",
            "ui-once@example.com",
            "StrongPassword123",
            "StrongPassword123",
        )
        assert "already been used" in error.lower()
        assert not is_authenticated(session)


class TestChatHandlers:
    def test_submit_displays_code_tests_requirements_and_pytest(
        self, api_env, fake_pipeline
    ) -> None:
        session, _ = handle_register(
            new_session(), "Dev", "dev@example.com", "StrongPassword123", "StrongPassword123"
        )
        session, kind, error = handle_submit(session, "Write a function that returns 42 for the caller")
        assert kind == "ok" and error == ""
        run = session["current_run"]
        assert run.generated_code and "def solution" in run.generated_code
        assert run.generated_tests and "def test_solution" in run.generated_tests
        req = requirements_markdown(run)
        assert "solution" in req
        summary = format_tests_summary(run)
        assert "3 tests passed" in summary
        message = assistant_message(run)
        assert "0.97" in message
        assert fake_pipeline.calls  # adapter invoked the shared pipeline

    def test_unsupported_sql_is_not_treated_as_python(self, api_env) -> None:
        pipeline = UnsupportedPipeline("sql")
        set_pipeline_runner(pipeline)
        session, _ = handle_register(
            new_session(), "Sql", "sql@example.com", "StrongPassword123", "StrongPassword123"
        )
        session, kind, _ = handle_submit(session, "Write an SQL query for top customers")
        assert kind == "ok"
        run = session["current_run"]
        assert run.status == "unsupported"
        assert run.task_type == "sql"
        assert not run.generated_code
        message = assistant_message(run)
        assert "not implemented" in message.lower()
        assert "def " not in message

    def test_failed_pytest_is_not_shown_as_success(self, api_env) -> None:
        set_pipeline_runner(FailingTestsPipeline())
        session, _ = handle_register(
            new_session(), "Fail", "fail@example.com", "StrongPassword123", "StrongPassword123"
        )
        session, kind, _ = handle_submit(session, "add two numbers")
        run = session["current_run"]
        assert run.status == "tests_failed"
        summary = format_tests_summary(run)
        assert "not a success" in summary.lower()
        exec_md = execution_markdown(run)
        assert "Tests passed: **no**" in exec_md

    def test_new_chat_clears_view_not_history(self, api_env, fake_pipeline) -> None:
        session, _ = handle_register(
            new_session(), "Hist", "hist@example.com", "StrongPassword123", "StrongPassword123"
        )
        handle_submit(session, "first task")
        handle_submit(session, "second task")
        assert len(handle_history(session)) == 2
        session = handle_new_chat(session)
        assert session["current_run"] is None
        assert session["conversation"] == []
        assert len(handle_history(session)) == 2

    def test_load_run_restores_artifacts(self, api_env, fake_pipeline) -> None:
        session, _ = handle_register(
            new_session(), "Load", "load@example.com", "StrongPassword123", "StrongPassword123"
        )
        handle_submit(session, "first")
        first_id = session["current_run"].id
        handle_submit(session, "second")
        session, error = handle_load_run(session, first_id)
        assert error == ""
        assert session["current_run"].id == first_id
        assert "first" in session["current_run"].sanitised_request


class TestUiIsolation:
    def test_separate_sessions_history_quota_and_logout(self, api_env, fake_pipeline) -> None:
        a, _ = handle_register(
            new_session(), "A", "iso-a@example.com", "StrongPassword123", "StrongPassword123"
        )
        b, _ = handle_register(
            new_session(), "B", "iso-b@example.com", "StrongPassword123", "StrongPassword123"
        )
        assert a["adapter"] is not b["adapter"]

        handle_submit(a, "alpha one")
        handle_submit(a, "alpha two")
        handle_submit(b, "beta one")

        runs_a = handle_history(a)
        runs_b = handle_history(b)
        assert len(runs_a) == 2 and all("alpha" in r.sanitised_request for r in runs_a)
        assert len(runs_b) == 1 and "beta" in runs_b[0].sanitised_request

        quota_a = handle_quota(a)
        quota_b = handle_quota(b)
        assert quota_a is not None and quota_a.used == 2
        assert quota_b is not None and quota_b.used == 1

        a = handle_logout(a)
        assert not is_authenticated(a)
        assert is_authenticated(b)
        assert len(handle_history(b)) == 1

    def test_concurrent_handler_sessions(self, api_env, fake_pipeline) -> None:
        def work(tag: str, count: int) -> list[str]:
            session, _ = handle_register(
                new_session(),
                tag,
                f"{tag}@example.com",
                "StrongPassword123",
                "StrongPassword123",
            )
            for i in range(count):
                handle_submit(session, f"{tag} task {i}")
            return [run.sanitised_request for run in handle_history(session)]

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(work, "concui-a", 3)
            future_b = pool.submit(work, "concui-b", 2)
            runs_a, runs_b = future_a.result(), future_b.result()

        assert len(runs_a) == 3 and all("concui-a" in item for item in runs_a)
        assert len(runs_b) == 2 and all("concui-b" in item for item in runs_b)


class TestQuotaHandler:
    def test_quota_exceeded_does_not_invoke_pipeline(
        self, api_env, fake_pipeline, monkeypatch
    ) -> None:
        from codeforge.config.settings import get_settings

        monkeypatch.setenv("MAX_RUNS_PER_USER_PER_DAY", "1")
        get_settings.cache_clear()
        try:
            session, _ = handle_register(
                new_session(),
                "Q",
                "quota-ui@example.com",
                "StrongPassword123",
                "StrongPassword123",
            )
            session, kind, _ = handle_submit(session, "one")
            assert kind == "ok"
            calls = len(fake_pipeline.calls)
            session, kind, error = handle_submit(session, "two")
            assert kind == "quota"
            assert "quota" in error.lower()
            assert len(fake_pipeline.calls) == calls
        finally:
            get_settings.cache_clear()


class TestInterfaceFactory:
    def test_build_interface_returns_blocks(self) -> None:
        from codeforge.ui.app import build_interface

        interface = build_interface()
        assert interface is not None
        assert hasattr(interface, "launch") or hasattr(interface, "queue")

    def test_application_factory_mounts_gradio(self, api_env, fake_pipeline) -> None:
        from fastapi.testclient import TestClient

        from codeforge.api.main import create_application

        with TestClient(create_application(include_gradio=True)) as client:
            docs = client.get("/docs")
            assert docs.status_code == 200
            ui = client.get("/ui")
            assert ui.status_code in (200, 307, 308)
            root = client.get("/", follow_redirects=False)
            assert root.status_code in (302, 307, 308)
            assert "/ui" in root.headers.get("location", "/ui")
