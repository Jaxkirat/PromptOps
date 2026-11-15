"""Token-to-principal resolution — the single trusted authentication path.

Both the FastAPI dependency and the Gradio adapter resolve identities through
:func:`resolve_principal_from_token`, so there is exactly one enforcement
point: signature + expiry verification, revocation check, database user
lookup, active check, and role resolution from trusted account data.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from codeforge.auth.identity import AuthenticatedPrincipal
from codeforge.auth.jwt_handler import decode_token
from codeforge.database.database import session_scope
from codeforge.database.models import RevokedToken
from codeforge.database.repositories import user_repository
from codeforge.exceptions import AuthenticationError


def resolve_principal_from_token(token: str) -> AuthenticatedPrincipal:
    """Fully verify ``token`` and return the trusted principal.

    Raises:
        AuthenticationError: invalid/expired/revoked token, unknown or
            inactive user.
    """
    payload = decode_token(token)
    jti: str = payload["jti"]
    user_id: str = payload["sub"]

    with session_scope() as db:
        if db.get(RevokedToken, jti) is not None:
            raise AuthenticationError("Token has been revoked.")

        user = user_repository.get_by_id(db, user_id)
        if user is None:
            raise AuthenticationError("Unknown user.")
        if not user.is_active:
            raise AuthenticationError("User account is inactive.")

        # Role comes from the database — never from a token claim.
        return AuthenticatedPrincipal(
            user_id=user.id,
            role=user.role,  # type: ignore[arg-type]
            email=user.email,
            is_active=user.is_active,
        )


def revoke_token(token: str) -> None:
    """Revoke the token's jti until its natural expiry (logout)."""
    payload = decode_token(token)
    expires_at = datetime.fromtimestamp(payload["exp"], tz=timezone.utc)
    try:
        with session_scope() as db:
            db.add(RevokedToken(jti=payload["jti"], expires_at=expires_at))
    except IntegrityError:
        pass  # already revoked — logout is idempotent
