"""Run data access.

Every query filters by owner. There is deliberately no function that fetches a
run by id alone — ownership is always part of the predicate, so cross-user
access is indistinguishable from a missing run.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from codeforge.database.models import Run


def create(db: Session, run: Run) -> Run:
    db.add(run)
    db.flush()
    return run


def list_for_owner(db: Session, owner_id: str) -> list[Run]:
    return list(
        db.execute(
            select(Run).where(Run.user_id == owner_id).order_by(Run.created_at.desc())
        ).scalars()
    )


def get_for_owner(db: Session, owner_id: str, run_id: str) -> Run | None:
    """Return the run only if it exists AND belongs to ``owner_id``."""
    return db.execute(
        select(Run).where(Run.id == run_id, Run.user_id == owner_id)
    ).scalar_one_or_none()
