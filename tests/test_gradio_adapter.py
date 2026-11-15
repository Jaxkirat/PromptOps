"""Gradio adapter plumbing tests — no UI, full enforcement parity."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from codeforge.exceptions import AuthenticationError, QuotaExceededError
from codeforge.integration.gradio_adapter import GradioSessionAdapter

SYNTHETIC_KEY = "sk-AdapterSecret1234567890abc"


class TestAdapterLifecycle:
    def test_register_login_submit_history_quota_logout(self, api_env, fake_pipeline) -> None:
        adapter = GradioSessionAdapter()
        profile = adapter.register("gradio@example.com", "StrongPassword123", "Gradio User")
        assert profile.role == "student"
        assert not adapter.is_authenticated

        profile = adapter.login("gradio@example.com", "StrongPassword123")
        assert adapter.is_authenticated
        assert profile.email == "gradio@example.com"

        run = adapter.submit_request("write a factorial function")
        assert run.status == "success"

        runs = adapter.my_runs()
        assert len(runs) == 1 and runs[0].id == run.id
        assert adapter.get_run(run.id).id == run.id

        quota = adapter.my_quota()
        assert quota.used == 1

        adapter.logout()
        assert not adapter.is_authenticated

    def test_adapter_never_exposes_token(self, api_env, fake_pipeline) -> None:
        adapter = GradioSessionAdapter()
        adapter.register("repr@example.com", "StrongPassword123", "R")
        adapter.login("repr@example.com", "StrongPassword123")
        assert "ey" not in repr(adapter)  # JWTs start with "ey"
        assert repr(adapter) == "<GradioSessionAdapter authenticated>"


class TestAdapterCannotBypassEnforcement:
    def test_cannot_bypass_authentication(self, api_env, fake_pipeline) -> None:
        adapter = GradioSessionAdapter()
        for operation in (
            adapter.profile,
            adapter.my_runs,
            adapter.my_quota,
            lambda: adapter.submit_request("task"),
            lambda: adapter.get_run("some-id"),
        ):
            with pytest.raises(AuthenticationError):
                operation()

    def test_logged_out_token_is_rejected(self, api_env, fake_pipeline) -> None:
        adapter = GradioSessionAdapter()
        adapter.register("revoked@example.com", "StrongPassword123", "R")
        adapter.login("revoked@example.com", "StrongPassword123")
        token = adapter._access_token
        adapter.logout()

        # Even resurrecting the old token fails: it was revoked server-side.
        adapter._access_token = token
        with pytest.raises(AuthenticationError):
            adapter.profile()

    def test_cannot_bypass_masking(self, api_env, fake_pipeline) -> None:
        adapter = GradioSessionAdapter()
        adapter.register("mask@example.com", "StrongPassword123", "M")
        adapter.login("mask@example.com", "StrongPassword123")

        run = adapter.submit_request(f"use my key {SYNTHETIC_KEY} please")
        assert SYNTHETIC_KEY not in fake_pipeline.calls[0]
        assert "[SECRET]" in fake_pipeline.calls[0]
        assert SYNTHETIC_KEY not in run.sanitised_request

    def test_cannot_bypass_quotas(self, api_env, fake_pipeline, monkeypatch) -> None:
        from codeforge.config.settings import get_settings

        monkeypatch.setenv("MAX_RUNS_PER_USER_PER_DAY", "2")
        get_settings.cache_clear()
        try:
            adapter = GradioSessionAdapter()
            adapter.register("adapterquota@example.com", "StrongPassword123", "Q")
            adapter.login("adapterquota@example.com", "StrongPassword123")
            adapter.submit_request("one")
            adapter.submit_request("two")
            with pytest.raises(QuotaExceededError):
                adapter.submit_request("three")
        finally:
            get_settings.cache_clear()


class TestConcurrentSessions:
    def test_concurrent_adapters_keep_identities_separate(
        self, api_env, fake_pipeline
    ) -> None:
        """Two sessions used concurrently must never see each other's data."""
        adapter_a = GradioSessionAdapter()
        adapter_b = GradioSessionAdapter()
        adapter_a.register("conc-a@example.com", "StrongPassword123", "A")
        adapter_b.register("conc-b@example.com", "StrongPassword123", "B")
        adapter_a.login("conc-a@example.com", "StrongPassword123")
        adapter_b.login("conc-b@example.com", "StrongPassword123")

        def work(adapter: GradioSessionAdapter, tag: str, count: int) -> list[str]:
            for i in range(count):
                adapter.submit_request(f"{tag} task {i}")
            return [run.sanitised_request for run in adapter.my_runs()]

        with ThreadPoolExecutor(max_workers=2) as pool:
            future_a = pool.submit(work, adapter_a, "alpha", 3)
            future_b = pool.submit(work, adapter_b, "beta", 2)
            runs_a, runs_b = future_a.result(), future_b.result()

        assert len(runs_a) == 3 and all("alpha" in r for r in runs_a)
        assert len(runs_b) == 2 and all("beta" in r for r in runs_b)

    def test_application_factory_exposes_gradio_mounting_point(self, api_env) -> None:
        import inspect

        from codeforge.api.main import create_application

        signature = inspect.signature(create_application)
        assert "include_gradio" in signature.parameters
        assert "mount_gradio_app" in inspect.getdoc(create_application)

        # The guard prevents premature mounting of an unfinished UI.
        with pytest.raises(NotImplementedError):
            create_application(include_gradio=True)
