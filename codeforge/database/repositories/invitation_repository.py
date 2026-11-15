"""Instructor invitation data access."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from codeforge.database.models import InstructorInvitation


def get_by_token_hash(db: Session, token_hash: str) -> InstructorInvitation | None:
    return db.execute(
        select(InstructorInvitation).where(InstructorInvitation.token_hash == token_hash)
    ).scalar_one_or_none()


def create(db: Session, invitation: InstructorInvitation) -> InstructorInvitation:
    db.add(invitation)
    db.flush()
    return invitation
