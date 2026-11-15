"""User data access."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from codeforge.database.models import User


def get_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(User.email == email.strip().lower())
    ).scalar_one_or_none()


def get_by_id(db: Session, user_id: str) -> User | None:
    return db.get(User, user_id)


def create(
    db: Session, *, email: str, password_hash: str, full_name: str, role: str
) -> User:
    user = User(
        email=email.strip().lower(),
        password_hash=password_hash,
        full_name=full_name.strip(),
        role=role,
    )
    db.add(user)
    db.flush()
    return user
