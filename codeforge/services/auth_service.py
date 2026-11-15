"""Authentication service: registration, login, logout, instructor provisioning."""

from __future__ import annotations

import logging

from email_validator import EmailNotValidError, validate_email

from codeforge.auth.jwt_handler import create_access_token
from codeforge.auth.password import hash_password, validate_password_strength, verify_password
from codeforge.auth.security import revoke_token
from codeforge.config.settings import get_settings
from codeforge.database.database import session_scope
from codeforge.database.models import ROLE_INSTRUCTOR, ROLE_STUDENT, User
from codeforge.database.repositories import user_repository
from codeforge.exceptions import AuthenticationError, RegistrationError

logger = logging.getLogger(__name__)


def _validate_email_format(email: str) -> str:
    try:
        return validate_email(email, check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise RegistrationError(f"Invalid email address: {exc}") from exc


def _create_user(email: str, password: str, full_name: str, role: str) -> User:
    normalized_email = _validate_email_format(email)
    validate_password_strength(password)
    if not full_name or not full_name.strip():
        raise RegistrationError("Full name must not be empty.")

    with session_scope() as db:
        if user_repository.get_by_email(db, normalized_email) is not None:
            raise RegistrationError("An account with this email already exists.")
        user = user_repository.create(
            db,
            email=normalized_email,
            password_hash=hash_password(password),
            full_name=full_name,
            role=role,
        )
        db.commit()
        logger.info("user_created user_id=%s role=%s", user.id, user.role)
        return user


def register_student(email: str, password: str, full_name: str) -> User:
    """Public registration. The role is ALWAYS student — any client-supplied
    role field is ignored upstream and never reaches this function."""
    return _create_user(email, password, full_name, ROLE_STUDENT)


def provision_instructor(email: str, password: str, full_name: str) -> User:
    """Trusted server-side instructor creation. Never exposed publicly."""
    return _create_user(email, password, full_name, ROLE_INSTRUCTOR)


def bootstrap_initial_instructor() -> None:
    """Create the initial instructor from trusted server-side configuration.

    Controlled by INITIAL_INSTRUCTOR_EMAIL / INITIAL_INSTRUCTOR_PASSWORD in the
    environment. Idempotent; credentials are never logged.
    """
    settings = get_settings()
    email = settings.initial_instructor_email
    password = settings.initial_instructor_password
    if not email or not password:
        return
    with session_scope() as db:
        if user_repository.get_by_email(db, email) is not None:
            return
    name = settings.initial_instructor_name or "Instructor"
    provision_instructor(email, password, name)
    logger.info("initial_instructor_provisioned")  # deliberately no email/credentials


def authenticate_user(email: str, password: str) -> tuple[str, int, User]:
    """Verify credentials and issue an access token.

    Returns:
        (access_token, expires_in_seconds, user)
    """
    with session_scope() as db:
        user = user_repository.get_by_email(db, email)
        if user is None or not verify_password(password, user.password_hash):
            # Identical error for unknown email and wrong password.
            raise AuthenticationError("Incorrect email or password.")
        if not user.is_active:
            raise AuthenticationError("User account is inactive.")

    token, _jti, expires_in = create_access_token(user.id)
    logger.info("user_login user_id=%s role=%s", user.id, user.role)
    return token, expires_in, user


def logout_user(token: str) -> None:
    """Invalidate the presented token (revocation by jti)."""
    revoke_token(token)
    logger.info("user_logout")
