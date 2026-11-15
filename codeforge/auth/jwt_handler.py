"""JWT creation and verification.

Token lifecycle:

1. Login issues a signed HS256 token with claims: ``sub`` (user id), ``jti``
   (unique token id), ``iat`` and ``exp`` (configurable minutes).
2. Every authenticated request verifies signature + expiry, checks the ``jti``
   against the revocation table, then loads the user from the database. The
   user's **role is never read from the token** — only from trusted account
   data — so a stale or tampered role claim is harmless.
3. Logout revokes the token's ``jti`` (stored until the token would have
   expired anyway), after which the token is rejected.

The signing secret comes from ``JWT_SECRET_KEY`` in the environment and is
never hardcoded or logged.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from codeforge.config.settings import Settings, get_settings
from codeforge.exceptions import AuthenticationError, ConfigurationError


def _require_secret(settings: Settings) -> str:
    if not settings.jwt_secret_key or len(settings.jwt_secret_key) < 32:
        raise ConfigurationError(
            "JWT_SECRET_KEY is missing or too short (need >= 32 characters). "
            "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(48))\" "
            "and set it in .env."
        )
    return settings.jwt_secret_key


def create_access_token(
    user_id: str,
    expires_minutes: int | None = None,
    settings: Settings | None = None,
) -> tuple[str, str, int]:
    """Create a signed access token.

    Returns:
        (token, jti, expires_in_seconds)
    """
    settings = settings or get_settings()
    secret = _require_secret(settings)
    minutes = (
        expires_minutes if expires_minutes is not None else settings.access_token_expire_minutes
    )
    now = datetime.now(timezone.utc)
    jti = uuid.uuid4().hex
    payload = {
        "sub": user_id,
        "jti": jti,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }
    token = jwt.encode(payload, secret, algorithm=settings.jwt_algorithm)
    return token, jti, minutes * 60


def decode_token(token: str, settings: Settings | None = None) -> dict[str, Any]:
    """Verify signature and expiry; return the claims.

    Raises:
        AuthenticationError: for any invalid, malformed or expired token.
    """
    settings = settings or get_settings()
    secret = _require_secret(settings)
    try:
        payload = jwt.decode(token, secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Token has expired.") from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationError("Invalid authentication token.") from exc

    if not payload.get("sub") or not payload.get("jti"):
        raise AuthenticationError("Invalid authentication token.")
    return payload
