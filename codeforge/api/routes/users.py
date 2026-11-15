"""User endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from codeforge.api.dependencies import get_current_principal
from codeforge.auth.identity import AuthenticatedPrincipal
from codeforge.services.quota_service import QuotaStatus, get_my_quota
from codeforge.services.user_service import UserProfile, get_current_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=UserProfile)
def my_profile(
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> UserProfile:
    return get_current_profile()


@router.get("/me/quota", response_model=QuotaStatus)
def my_quota(
    _principal: AuthenticatedPrincipal = Depends(get_current_principal),
) -> QuotaStatus:
    return get_my_quota()
