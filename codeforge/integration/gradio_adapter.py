"""Gradio adapter plumbing (Phase 3 readiness — NO UI components here).

:class:`GradioSessionAdapter` is the bridge the Phase 3 Gradio callbacks will
use. One adapter instance is created per Gradio browser session (e.g. stored
in ``gr.State``), which keeps authenticated sessions for concurrent users
fully separate:

- It holds ONLY the session's access token — never a password, never the JWT
  secret, never any global mutable state.
- Every operation re-verifies the token through the exact same trusted path as
  the HTTP API (``authenticated_context``), so Gradio cannot bypass
  authentication, masking, quotas or ownership checks.
- The token is never logged and ``repr()`` never exposes it.

Same-process service calls are preferred (no loopback HTTP), but because the
FastAPI routes remain mounted in the same application, a future Gradio page
could equally call them over HTTP with the same token — both paths share one
enforcement implementation.
"""

from __future__ import annotations

from codeforge.exceptions import AuthenticationError
from codeforge.integration import codeforge_service as services
from codeforge.services.quota_service import QuotaStatus
from codeforge.services.run_service import RunRecord
from codeforge.services.user_service import UserProfile


class GradioSessionAdapter:
    """Session-scoped backend access for the future Gradio interface."""

    def __init__(self) -> None:
        self._access_token: str | None = None

    def __repr__(self) -> str:  # never leak the token
        state = "authenticated" if self.is_authenticated else "anonymous"
        return f"<GradioSessionAdapter {state}>"

    # -- Session lifecycle ---------------------------------------------------

    @property
    def is_authenticated(self) -> bool:
        return self._access_token is not None

    def register(self, email: str, password: str, full_name: str) -> UserProfile:
        """Register a new student account (role is always student)."""
        return services.register_user(email, password, full_name)

    def login(self, email: str, password: str) -> UserProfile:
        """Authenticate and keep the access token scoped to this session only."""
        token, _expires_in, profile = services.login(email, password)
        self._access_token = token
        return profile

    def logout(self) -> None:
        """Revoke this session's token and clear it."""
        if self._access_token is not None:
            services.logout(self._access_token)
            self._access_token = None

    # -- Authenticated operations ---------------------------------------------

    def _require_token(self) -> str:
        if self._access_token is None:
            raise AuthenticationError("Not authenticated.")
        return self._access_token

    def profile(self) -> UserProfile:
        with services.authenticated_context(self._require_token()):
            return services.get_current_profile()

    def submit_request(self, request_text: str) -> RunRecord:
        """Submit a coding request through the full privacy/quota pipeline."""
        with services.authenticated_context(self._require_token()):
            return services.submit_code_request(request_text)

    def my_runs(self) -> list[RunRecord]:
        with services.authenticated_context(self._require_token()):
            return services.get_my_runs()

    def get_run(self, run_id: str) -> RunRecord:
        with services.authenticated_context(self._require_token()):
            return services.get_run(run_id)

    def my_quota(self) -> QuotaStatus:
        with services.authenticated_context(self._require_token()):
            return services.get_my_quota()
