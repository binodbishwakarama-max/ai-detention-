"""
Authentication endpoints.

Handles user registration, login, token refresh, and API key management.
All operations are audit-logged.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import ORJSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from src.api.deps import (
    CurrentUser,
    DbSession,
    RequireAdmin,
    get_client_ip,
)
from src.config import get_settings
from src.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyResponse,
    TokenRefresh,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
)
from src.schemas.common import MessageResponse
from src.services import auth_service

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user and organization",
)
async def register(
    request: Request,
    body: UserCreate,
    db: DbSession,
) -> UserResponse:
    """
    Register a new user and create their organization.

    The first user is automatically assigned the ADMIN role.
    """
    ip = get_client_ip(request)
    user, org = await auth_service.register_user(
        db,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        organization_name=body.organization_name,
        ip_address=ip,
    )
    return UserResponse.model_validate(user)


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate with email and password",
)
async def login(
    request: Request,
    body: UserLogin,
    db: DbSession,
) -> TokenResponse:
    """Returns a JWT access/refresh token pair on successful authentication."""
    ip = get_client_ip(request)
    settings = get_settings()
    access_token, refresh_token, user = (
        await auth_service.authenticate_user(
            db,
            email=body.email,
            password=body.password,
            ip_address=ip,
        )
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh an access token",
)
async def refresh_token(
    body: TokenRefresh,
    db: DbSession,
) -> TokenResponse:
    """Issue a new access token using a valid refresh token."""
    settings = get_settings()
    access_token, new_refresh = await auth_service.refresh_access_token(
        db, refresh_token_str=body.refresh_token
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=new_refresh,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def get_me(user: CurrentUser) -> UserResponse:
    """Return the authenticated user's profile."""
    return UserResponse.model_validate(user)


# ── API Key Management ──────────────────────────────────


@router.post(
    "/api-keys",
    response_model=ApiKeyCreated,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new API key",
)
async def create_api_key(
    request: Request,
    body: ApiKeyCreate,
    user: CurrentUser,
    db: DbSession,
) -> ApiKeyCreated:
    """
    Create a new API key for programmatic access.

    The raw key is returned only once in this response.
    Store it securely — it cannot be retrieved again.
    """
    ip = get_client_ip(request)
    api_key, raw_key = await auth_service.create_api_key_for_user(
        db,
        user_id=user.id,
        org_id=user.organization_id,
        name=body.name,
        scopes=body.scopes,
        expires_in_days=body.expires_in_days,
        ip_address=ip,
    )
    response = ApiKeyCreated.model_validate(api_key)
    response.raw_key = raw_key
    return response


@router.delete(
    "/api-keys/{key_id}",
    response_model=MessageResponse,
    summary="Revoke an API key",
    dependencies=[RequireAdmin],
)
async def revoke_api_key(
    request: Request,
    key_id: str,
    user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    """Permanently revoke an API key. This action cannot be undone."""
    from uuid import UUID

    ip = get_client_ip(request)
    await auth_service.revoke_api_key(
        db,
        key_id=UUID(key_id),
        org_id=user.organization_id,
        user_id=user.id,
        ip_address=ip,
    )
    return MessageResponse(message="API key revoked successfully")
