"""
FastAPI dependency injection providers.

Centralizes all dependencies used across API routes:
- Database sessions
- Authentication (JWT + API key)
- Authorization (role-based access control)
- Pagination parameters
- Request metadata (IP, user agent)

All dependencies are async-compatible and designed for the FastAPI
Depends() injection system.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import get_settings
from src.database import get_db_session
from src.middleware.error_handler import ForbiddenError, UnauthorizedError
from src.models.user import User
from src.schemas.common import PaginationParams
from src.security import Role, TokenType, decode_token, has_permission

# ── Security Schemes ────────────────────────────────────────
bearer_scheme = HTTPBearer(auto_error=False)

# ── Type Aliases ────────────────────────────────────────────
DbSession = Annotated[AsyncSession, Depends(get_db_session)]


# ── Authentication ──────────────────────────────────────────


async def get_current_user(
    request: Request,
    db: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ] = None,
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> User:
    """
    Authenticate the current request via JWT or API key.

    Priority:
    1. Bearer token (JWT) in Authorization header
    2. API key in X-API-Key header

    Sets request.state.user_id and request.state.org_id for downstream use
    (rate limiter, audit middleware).
    """
    user: User | None = None

    # Try JWT first
    if credentials and credentials.credentials:
        try:
            payload = decode_token(credentials.credentials)
        except Exception:
            raise UnauthorizedError("Invalid or expired access token")

        if payload.get("type") != TokenType.ACCESS.value:
            raise UnauthorizedError(
                "Invalid token type — use an access token"
            )

        user_id = UUID(payload["sub"])
        org_id = UUID(payload["org"])

        from sqlalchemy import select

        result = await db.execute(
            select(User).where(
                User.id == user_id,
                User.is_active == True,  # noqa: E712
                User.is_deleted == False,  # noqa: E712
            )
        )
        user = result.scalar_one_or_none()
        if not user:
            raise UnauthorizedError("User not found or deactivated")

    # Try API key
    elif x_api_key:
        from src.services.auth_service import authenticate_api_key

        client_ip = (
            request.client.host if request.client else None
        )
        user, _ = await authenticate_api_key(
            db, raw_key=x_api_key, ip_address=client_ip
        )

    else:
        # Development bypass: Automatically authenticate as the first user
        # if no credentials provided and we are in DEVELOPMENT mode.
        settings = get_settings()
        if settings.is_development:
            from sqlalchemy import select
            result = await db.execute(
                select(User).where(
                    User.is_active == True,  # noqa: E712
                    User.is_deleted == False,  # noqa: E712
                ).order_by(User.created_at.asc()).limit(1)
            )
            user = result.scalar_one_or_none()
            
            if user:
                from structlog import get_logger
                get_logger(__name__).warning("auth.dev_bypass_active", user_id=str(user.id))
            else:
                raise UnauthorizedError("Development bypass failed: No users exist in database")
        else:
            raise UnauthorizedError(
                "Authentication required — provide a Bearer token or API key"
            )

    # Set request state for middleware
    request.state.user_id = str(user.id)
    request.state.org_id = str(user.organization_id)

    return user


# ── Typed Dependencies ──────────────────────────────────────
CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(required_role: Role):
    """
    Dependency factory for role-based access control.

    Usage:
        @router.post("/admin-only", dependencies=[Depends(require_role(Role.ADMIN))])
    """

    async def check_role(user: CurrentUser) -> User:
        if not has_permission(user.role, required_role):
            raise ForbiddenError(
                f"This action requires '{required_role.value}' role or higher"
            )
        return user

    return check_role


# Convenience aliases for common role checks
RequireAdmin = Depends(require_role(Role.ADMIN))
RequireMember = Depends(require_role(Role.MEMBER))
RequireViewer = Depends(require_role(Role.VIEWER))


# ── Pagination ──────────────────────────────────────────────


async def get_pagination(
    page: int = 1,
    page_size: int = 20,
) -> PaginationParams:
    """Dependency that validates and returns pagination parameters."""
    return PaginationParams(page=max(1, page), page_size=min(100, max(1, page_size)))


Pagination = Annotated[PaginationParams, Depends(get_pagination)]


# ── Request Metadata ────────────────────────────────────────


def get_client_ip(request: Request) -> str:
    """Extract client IP, respecting X-Forwarded-For behind a proxy."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # Take the first IP (client) from the chain
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
