"""User profile service."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from codeforge.auth.identity import current_principal
from codeforge.database.database import session_scope
from codeforge.database.repositories import user_repository
from codeforge.exceptions import AuthenticationError


class UserProfile(BaseModel):
    """Safe, public-facing user information (never includes password hashes)."""

    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


def get_current_profile() -> UserProfile:
    """Profile of the authenticated user (identity from request context)."""
    principal = current_principal()
    with session_scope() as db:
        user = user_repository.get_by_id(db, principal.user_id)
        if user is None:
            raise AuthenticationError("Unknown user.")
        return UserProfile(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            is_active=user.is_active,
            created_at=user.created_at,
        )


def profile_from_user(user) -> UserProfile:
    """Build a safe profile from an ORM user (used right after register/login)."""
    return UserProfile(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=user.is_active,
        created_at=user.created_at,
    )
