"""Trusted request-scoped identity.

:class:`AuthenticatedPrincipal` is only ever constructed after full token
verification and a database lookup (see :mod:`codeforge.auth.security`). It is
then bound to a :class:`contextvars.ContextVar`, giving every service in the
call chain access to the authenticated identity **without any user_id
parameters** — and safely under concurrency, because ContextVars are isolated
per task/thread context (unlike a shared mutable global).

Frontends can never supply this identity; user messages can never alter it.
"""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Literal

from pydantic import BaseModel, ConfigDict

from codeforge.exceptions import AuthenticationError


class AuthenticatedPrincipal(BaseModel):
    """Server-side verified identity of the requesting user."""

    model_config = ConfigDict(frozen=True)

    user_id: str
    role: Literal["student", "instructor"]
    email: str
    is_active: bool


_current_principal: ContextVar[AuthenticatedPrincipal | None] = ContextVar(
    "codeforge_current_principal", default=None
)


def current_principal() -> AuthenticatedPrincipal:
    """Return the authenticated principal for the current request context.

    Raises:
        AuthenticationError: if no verified identity is bound to this context.
    """
    principal = _current_principal.get()
    if principal is None:
        raise AuthenticationError("Not authenticated.")
    return principal


def maybe_current_principal() -> AuthenticatedPrincipal | None:
    """Return the bound principal or None (used by logging middleware)."""
    return _current_principal.get()


@contextmanager
def principal_context(principal: AuthenticatedPrincipal) -> Iterator[None]:
    """Bind ``principal`` to the current execution context for the duration.

    Used by the FastAPI dependency and by trusted non-HTTP callers (Gradio
    adapter, background jobs with an explicit trusted job context).
    """
    token = _current_principal.set(principal)
    try:
        yield
    finally:
        _current_principal.reset(token)
