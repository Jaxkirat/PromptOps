"""Authentication API schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from codeforge.services.user_service import UserProfile


class RegisterRequest(BaseModel):
    """Public registration payload.

    Extra fields (including any client-supplied ``role``) are silently ignored:
    public registration ALWAYS creates a student account.
    """

    model_config = ConfigDict(extra="ignore")

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    full_name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    email: EmailStr
    password: str = Field(min_length=1, max_length=256)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserProfile


class MessageResponse(BaseModel):
    detail: str


class InvitationValidateRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    token: str = Field(min_length=1, max_length=512)


class InvitationAcceptRequest(BaseModel):
    """Instructor invitation activation. Role is assigned server-side."""

    model_config = ConfigDict(extra="ignore")

    token: str = Field(min_length=1, max_length=512)
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    full_name: str = Field(min_length=1, max_length=255)


class InvitationPreviewResponse(BaseModel):
    email: str
    expires_at: str
    status: str
