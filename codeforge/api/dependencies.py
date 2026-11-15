"""FastAPI dependencies: trusted identity resolution and role requirements.

``get_current_principal`` is the ONLY way a request obtains an identity:
token extraction -> signature/expiry validation -> revocation check ->
database user lookup -> active check -> role from trusted account data.
The verified principal is bound to the request context (ContextVar) so
services resolve identity internally without user_id parameters.
"""

from __future__ import annotations

from typing import AsyncIterator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from codeforge.auth.identity import AuthenticatedPrincipal, principal_context
from codeforge.auth.security import resolve_principal_from_token
from codeforge.database.models import ROLE_INSTRUCTOR, ROLE_STUDENT
from codeforge.exceptions import AuthenticationError

_bearer_scheme = HTTPBearer(auto_error=False)


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> str:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return credentials.credentials


async def get_current_principal(
    token: str = Depends(get_bearer_token),
) -> AsyncIterator[AuthenticatedPrincipal]:
    """Resolve and bind the trusted principal for the duration of the request."""
    try:
        principal = resolve_principal_from_token(token)
    except AuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    with principal_context(principal):
        yield principal


def _require_role(role: str):
    async def dependency(
        principal: AuthenticatedPrincipal = Depends(get_current_principal),
    ) -> AuthenticatedPrincipal:
        if principal.role != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"This action requires the '{role}' role.",
            )
        return principal

    return dependency


require_student = _require_role(ROLE_STUDENT)
require_instructor = _require_role(ROLE_INSTRUCTOR)
