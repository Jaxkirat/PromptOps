"""User API schemas (re-exported from the service layer to avoid duplication)."""

from codeforge.services.quota_service import QuotaStatus
from codeforge.services.user_service import UserProfile

__all__ = ["QuotaStatus", "UserProfile"]
