"""Per-user daily quota management (UTC), enforced in Python with atomic
database reservations.

The reservation is a conditional UPDATE (``reserved_count < limit``) inside a
transaction, so concurrent requests cannot exceed the configured limit.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel
from sqlalchemy import insert, update
from sqlalchemy.exc import IntegrityError

from codeforge.auth.identity import current_principal
from codeforge.config.settings import get_settings
from codeforge.database.database import session_scope
from codeforge.database.models import QuotaUsage
from codeforge.exceptions import QuotaExceededError

logger = logging.getLogger(__name__)


class QuotaStatus(BaseModel):
    """Quota snapshot for one user on the current UTC day."""

    limit: int
    used: int
    remaining: int
    utc_date: str
    resets_at: str


def _utc_today():
    return datetime.now(timezone.utc).date()


def _ensure_row(user_id: str, limit: int) -> None:
    """Make sure today's quota row exists (races resolved by the unique constraint)."""
    try:
        with session_scope() as db:
            db.execute(
                insert(QuotaUsage).values(
                    user_id=user_id,
                    usage_date=_utc_today(),
                    reserved_count=0,
                    quota_limit=limit,
                )
            )
    except IntegrityError:
        pass  # row already exists for (user, date)


def reserve_run(user_id: str) -> None:
    """Atomically reserve one run for ``user_id`` today.

    Raises:
        QuotaExceededError: if the daily limit is already fully reserved.
    """
    limit = get_settings().max_runs_per_user_per_day
    _ensure_row(user_id, limit)

    with session_scope() as db:
        result = db.execute(
            update(QuotaUsage)
            .where(
                QuotaUsage.user_id == user_id,
                QuotaUsage.usage_date == _utc_today(),
                QuotaUsage.reserved_count < limit,
            )
            .values(reserved_count=QuotaUsage.reserved_count + 1)
        )
        if result.rowcount == 0:
            logger.info("quota_rejected user_id=%s limit=%d", user_id, limit)
            raise QuotaExceededError(
                f"Daily run quota of {limit} exhausted. Quota resets at midnight UTC."
            )


def get_my_quota() -> QuotaStatus:
    """Quota status for the authenticated user (identity from request context)."""
    principal = current_principal()
    limit = get_settings().max_runs_per_user_per_day
    today = _utc_today()
    with session_scope() as db:
        row = (
            db.query(QuotaUsage)
            .filter(QuotaUsage.user_id == principal.user_id, QuotaUsage.usage_date == today)
            .one_or_none()
        )
        used = row.reserved_count if row is not None else 0
    resets_at = datetime.combine(
        today + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    )
    return QuotaStatus(
        limit=limit,
        used=used,
        remaining=max(limit - used, 0),
        utc_date=today.isoformat(),
        resets_at=resets_at.isoformat(),
    )
