"""Authentication endpoints. Thin controllers over the auth service."""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from codeforge.api.dependencies import get_bearer_token, get_current_principal
from codeforge.api.schemas.auth import (
    LoginRequest,
    MessageResponse,
    RegisterRequest,
    TokenResponse,
)
from codeforge.auth.identity import AuthenticatedPrincipal
from codeforge.services import auth_service
from codeforge.services.user_service import UserProfile, get_current_profile, profile_from_user

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=UserProfile, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest) -> UserProfile:
    """Public student registration. Any supplied role field is ignored —
    the account is ALWAYS created with role=student."""
    user = auth_service.register_student(
        email=payload.email, password=payload.password, full_name=payload.full_name
    )
    return profile_from_user(user)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    token, expires_in, user = auth_service.authenticate_user(payload.email, payload.password)
    return TokenResponse(
        access_token=token, expires_in=expires_in, user=profile_from_user(user)
    )


@router.post("/logout", response_model=MessageResponse)
def logout(
    token: str = Depends(get_bearer_token),
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> MessageResponse:
    """Invalidate the presented access token (jti revocation)."""
    auth_service.logout_user(token)
    return MessageResponse(detail="Logged out.")


@router.get("/me", response_model=UserProfile)
def me(_principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> UserProfile:
    return get_current_profile()
