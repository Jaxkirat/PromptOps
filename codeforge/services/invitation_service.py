"""Trusted instructor invitation workflow.

Invitations are generated only through the CLI (or other trusted server-side
code). The plaintext token is shown once and never persisted — only a SHA-256
hash is stored. Acceptance creates an instructor account server-side; the
frontend cannot assign the role.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel

from codeforge.config.settings import get_settings
from codeforge.database.database import session_scope
from codeforge.database.models import ROLE_INSTRUCTOR, InstructorInvitation
from codeforge.database.repositories import invitation_repository, user_repository
from codeforge.exceptions import InvitationError
from codeforge.services.auth_service import _create_user, _validate_email_format

logger = logging.getLogger(__name__)


class InvitationPreview(BaseModel):
    """Safe invitation metadata — never includes the raw token or its hash."""

    email: str
    expires_at: datetime
    status: str


class CreatedInvitation(BaseModel):
    """Returned only to the trusted CLI that generated the invite."""

    email: str
    expires_at: datetime
    invite_url: str
    expires_in_hours: int


def hash_invitation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def create_instructor_invitation(
    email: str, expires_hours: int | None = None
) -> CreatedInvitation:
    """Create a single-use invitation. Returns the plaintext URL once."""
    settings = get_settings()
    normalized = _validate_email_format(email)
    hours = expires_hours if expires_hours is not None else settings.invite_expiry_hours
    if hours <= 0:
        raise InvitationError("Invitation expiry must be a positive number of hours.")

    token = secrets.token_urlsafe(32)
    expires_at = _utcnow() + timedelta(hours=hours)
    invitation = InstructorInvitation(
        token_hash=hash_invitation_token(token),
        email=normalized,
        expires_at=expires_at,
        created_by="cli",
    )
    with session_scope() as db:
        invitation_repository.create(db, invitation)
        db.commit()

    invite_url = f"{settings.app_base_url}/ui/?token={token}"
    logger.info(
        "instructor_invitation_created email_domain=%s expires_at=%s",
        normalized.split("@", 1)[-1],
        expires_at.isoformat(),
    )
    return CreatedInvitation(
        email=normalized,
        expires_at=expires_at,
        invite_url=invite_url,
        expires_in_hours=hours,
    )


def _load_invitation(token: str) -> InstructorInvitation:
    if not token or not token.strip():
        raise InvitationError("Invalid invitation.")
    token_hash = hash_invitation_token(token.strip())
    with session_scope() as db:
        invitation = invitation_repository.get_by_token_hash(db, token_hash)
        if invitation is None:
            raise InvitationError("Invalid invitation.")
        # Detach fields we need after the session closes.
        db.expunge(invitation)
        return invitation


def _status_for(invitation: InstructorInvitation) -> str:
    now = _utcnow()
    if invitation.used_at is not None:
        return "used"
    if _aware(invitation.expires_at) <= now:
        return "expired"
    return "valid"


def validate_invitation(token: str) -> InvitationPreview:
    """Return safe preview data, or raise :class:`InvitationError`."""
    invitation = _load_invitation(token)
    status = _status_for(invitation)
    if status == "used":
        raise InvitationError("Invitation has already been used.")
    if status == "expired":
        raise InvitationError("Invitation has expired.")
    return InvitationPreview(
        email=invitation.email, expires_at=_aware(invitation.expires_at), status=status
    )


def accept_invitation(token: str, email: str, password: str, full_name: str):
    """Consume a valid invitation and create an instructor account.

    The instructor role is assigned here on the server — never by the client.
    """
    invitation = _load_invitation(token)
    status = _status_for(invitation)
    if status == "used":
        raise InvitationError("Invitation has already been used.")
    if status == "expired":
        raise InvitationError("Invitation has expired.")

    normalized = _validate_email_format(email)
    if normalized != invitation.email:
        raise InvitationError("This invitation is restricted to a different email.")

    # Create the instructor first so a duplicate-email failure does not consume
    # the invitation. Then mark it used in the same logical sequence.
    user = _create_user(normalized, password, full_name, ROLE_INSTRUCTOR)

    now = _utcnow()
    with session_scope() as db:
        stored = invitation_repository.get_by_token_hash(
            db, hash_invitation_token(token.strip())
        )
        if stored is None or stored.used_at is not None:
            raise InvitationError("Invitation has already been used.")
        stored.used_at = now
        db.commit()

    logger.info("instructor_invitation_accepted user_id=%s", user.id)
    return user


