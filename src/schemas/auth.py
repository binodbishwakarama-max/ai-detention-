"""Authentication and authorization schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator

from src.schemas.common import BaseSchema, TimestampSchema
from src.security import Role


# ── Registration / Login ─────────────────────────────────


class UserCreate(BaseModel):
    """Schema for user registration."""

    email: EmailStr = Field(description="User email address")
    password: str = Field(
        min_length=8, max_length=128, description="Password (min 8 chars)"
    )
    full_name: str = Field(
        min_length=1, max_length=255, description="Full name"
    )
    organization_name: str = Field(
        min_length=1, max_length=255, description="Organization name"
    )

    @field_validator("password")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        """Enforce password complexity requirements (Temporarily relaxed for DEV)."""
        # if not any(c.isupper() for c in v):
        #     raise ValueError(
        #         "Password must contain at least one uppercase letter"
        #     )
        # if not any(c.islower() for c in v):
        #     raise ValueError(
        #         "Password must contain at least one lowercase letter"
        #     )
        # if not any(c.isdigit() for c in v):
        #     raise ValueError("Password must contain at least one digit")
        # if not any(c in "!@#$%^&*()_+-=[]{}|;:',.<>?/" for c in v):
        #     raise ValueError(
        #         "Password must contain at least one special character"
        #     )
        return v


class UserLogin(BaseModel):
    """Schema for user login."""

    email: EmailStr
    password: str


class TokenResponse(BaseSchema):
    """JWT token pair returned after authentication."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token TTL in seconds")


class TokenRefresh(BaseModel):
    """Schema for token refresh."""

    refresh_token: str


class UserResponse(TimestampSchema):
    """Public user representation (never includes password hash)."""

    id: UUID
    email: str
    full_name: str
    role: Role
    organization_id: UUID
    is_active: bool
    mfa_enabled: bool
    last_login_at: datetime | None


class UserUpdate(BaseModel):
    """Schema for updating user profile."""

    full_name: str | None = None
    role: Role | None = None
    is_active: bool | None = None


# ── API Keys ─────────────────────────────────────────────


class ApiKeyCreate(BaseModel):
    """Schema for creating an API key."""

    name: str = Field(min_length=1, max_length=255, description="Key name")
    scopes: list[str] = Field(
        default=["evaluations:read"],
        description="Permission scopes",
    )
    expires_in_days: int | None = Field(
        default=None,
        ge=1,
        le=365,
        description="Key TTL in days (NULL = never expires)",
    )


class ApiKeyResponse(TimestampSchema):
    """API key response (never includes the hash)."""

    id: UUID
    name: str
    key_prefix: str
    scopes: list[str]
    expires_at: datetime | None
    last_used_at: datetime | None
    is_revoked: bool


class ApiKeyCreated(ApiKeyResponse):
    """
    Response returned exactly once when a key is created.
    Contains the raw key — this is the only time it's visible.
    """

    raw_key: str = Field(
        description=(
            "The raw API key — store it securely, it won't be shown again"
        )
    )
