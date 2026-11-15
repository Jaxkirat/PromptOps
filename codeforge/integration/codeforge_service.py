"""Shared CodeForge application service layer.

One HTTP-independent facade used by BOTH the FastAPI routes and the future
Gradio interface, so authentication, masking, quota and ownership logic exists
exactly once. FastAPI routes are thin controllers over these functions; Gradio
callbacks (Phase 3) will call them through the session adapter.

Identity-aware functions resolve the caller from the trusted request context —
bind it first with :func:`authenticated_context` (non-HTTP callers) or via the
FastAPI dependency (HTTP callers).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from codeforge.auth.identity import principal_context
from codeforge.auth.security import resolve_principal_from_token
from codeforge.services.auth_service import (
    authenticate_user,
    logout_user,
    provision_instructor,
    register_student,
)
from codeforge.services.invitation_service import (
    InvitationPreview,
    accept_invitation,
    validate_invitation,
)
from codeforge.services.quota_service import QuotaStatus, get_my_quota
from codeforge.services.run_service import (
    RunRecord,
    get_my_runs,
    get_run,
    set_pipeline_runner,
    submit_code_request,
)
from codeforge.services.user_service import UserProfile, get_current_profile, profile_from_user


@contextmanager
def authenticated_context(access_token: str) -> Iterator[None]:
    """Verify ``access_token`` and bind the trusted identity for the block.

    The exact same verification path as the HTTP API (signature, expiry,
    revocation, user lookup, active check, DB role) — no bypass exists for
    non-HTTP callers.
    """
    principal = resolve_principal_from_token(access_token)
    with principal_context(principal):
        yield


def register_user(email: str, password: str, full_name: str) -> UserProfile:
    """Public registration (always role=student)."""
    return profile_from_user(register_student(email, password, full_name))


def login(email: str, password: str) -> tuple[str, int, UserProfile]:
    """Authenticate and return (access_token, expires_in_seconds, profile)."""
    token, expires_in, user = authenticate_user(email, password)
    return token, expires_in, profile_from_user(user)


def logout(access_token: str) -> None:
    """Revoke the access token."""
    logout_user(access_token)


def preview_invitation(token: str) -> InvitationPreview:
    """Validate an instructor invitation without consuming it."""
    return validate_invitation(token)


def activate_invitation(token: str, email: str, password: str, full_name: str) -> UserProfile:
    """Consume an invitation and create an instructor account (server-assigned role)."""
    return profile_from_user(accept_invitation(token, email, password, full_name))


__all__ = [
    "authenticated_context",
    "register_user",
    "login",
    "logout",
    "provision_instructor",
    "get_current_profile",
    "submit_code_request",
    "get_my_runs",
    "get_run",
    "get_my_quota",
    "set_pipeline_runner",
    "preview_invitation",
    "activate_invitation",
    "QuotaStatus",
    "RunRecord",
    "UserProfile",
    "InvitationPreview",
]
