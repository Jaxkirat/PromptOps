"""Fingerprints of data the SQL agent must not change.

Audit rows are excluded: recording a rejected query is expected to add a row.
"""

from __future__ import annotations

import hashlib
import json

from codeforge.database.database import session_scope
from codeforge.database.models import Run, User
from codeforge.sql_agent.sample_db import sample_user_rows


def storage_fingerprint() -> str:
    with session_scope() as session:
        users = [
            (row.id, row.email, row.password_hash, row.role, row.full_name)
            for row in session.query(User).order_by(User.id).all()
        ]
        runs = [
            (row.id, row.user_id, row.sanitised_request, row.generated_code, row.status)
            for row in session.query(Run).order_by(Run.id).all()
        ]
    payload = {
        "users": users,
        "runs": runs,
        "sample_users": sample_user_rows(),
    }
    encoded = json.dumps(payload, default=str, sort_keys=True)
    return hashlib.sha256(encoded.encode()).hexdigest()
