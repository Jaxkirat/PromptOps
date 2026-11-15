"""Role checks for authorization.

Both roles may use the ordinary code-generation pipeline. Instructor-only
functionality arrives with R7; the check is already available here.
"""

from __future__ import annotations

from codeforge.auth.identity import AuthenticatedPrincipal
from codeforge.database.models import ROLE_INSTRUCTOR, ROLE_STUDENT
from codeforge.exceptions import AuthorizationError


def require_role(principal: AuthenticatedPrincipal, role: str) -> AuthenticatedPrincipal:
    if principal.role != role:
        raise AuthorizationError(f"This action requires the '{role}' role.")
    return principal


def ensure_student(principal: AuthenticatedPrincipal) -> AuthenticatedPrincipal:
    return require_role(principal, ROLE_STUDENT)


def ensure_instructor(principal: AuthenticatedPrincipal) -> AuthenticatedPrincipal:
    return require_role(principal, ROLE_INSTRUCTOR)
