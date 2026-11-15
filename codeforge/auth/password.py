"""Password hashing (Argon2) and password policy validation.

Plaintext passwords exist only transiently in memory; they are never logged or
persisted. Only Argon2 hashes are stored.
"""

from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

from codeforge.exceptions import RegistrationError

_hasher = PasswordHasher()

MIN_PASSWORD_LENGTH = 8


def validate_password_strength(password: str) -> None:
    """Enforce the password policy; raise :class:`RegistrationError` if weak."""
    if len(password) < MIN_PASSWORD_LENGTH:
        raise RegistrationError(
            f"Password must be at least {MIN_PASSWORD_LENGTH} characters long."
        )
    if not re.search(r"[A-Za-z]", password):
        raise RegistrationError("Password must contain at least one letter.")
    if not re.search(r"\d", password):
        raise RegistrationError("Password must contain at least one digit.")


def hash_password(password: str) -> str:
    """Hash a password with Argon2id."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Constant-time-ish verification; never raises on mismatch."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, ValueError):
        return False
