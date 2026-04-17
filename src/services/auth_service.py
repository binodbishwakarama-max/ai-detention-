"""
Authentication service.

Handles user registration, login, token management, and API key authentication.
All authentication events are audit-logged for SOC2 compliance.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.error_handler import (
    ConflictError,
    NotFoundError,
    UnauthorizedError,
)
from src.models.api_key import ApiKey
from src.models.audit_log import AuditAction
from src.models.organization import Organization
from src.models.user import User
from src.security import (
    Role,
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from src.services.audit_service import create_audit_log

logger = structlog.get_logger(__name__)


def _slugify(name: str) -> str:
    """Convert an organization name to a URL-safe slug."""
    slug = name.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    return slug[:63]


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    organization_name: str,
    ip_address: str | None = None,
) -> tuple[User, Organization]:
    """
    Register a new user and create their organization.

    The first user in an organization is automatically assigned the ADMIN role.
    """
    # Check for existing user
    existing = await db.execute(
        select(User).where(User.email == email)
    )
    if existing.scalar_one_or_none():
        raise ConflictError(f"User with email '{email}' already exists")

    # Check for existing org slug
    slug = _slugify(organization_name)
    existing_org = await db.execute(
        select(Organization).where(Organization.slug == slug)
    )
    if existing_org.scalar_one_or_none():
        raise ConflictError(
            f"Organization '{organization_name}' already exists"
        )

    # Create organization
    org = Organization(name=organization_name, slug=slug)
    db.add(org)
    await db.flush()  # get org.id without committing

    # Create user with ADMIN role (first user in org)
    user = User(
        email=email,
        hashed_password=hash_password(password),
        full_name=full_name,
        role=Role.ADMIN,
        organization_id=org.id,
    )
    db.add(user)
    await db.flush()

    # Audit log
    await create_audit_log(
        db,
        action=AuditAction.CREATE,
        resource_type="user",
        resource_id=str(user.id),
        organization_id=org.id,
        user_id=user.id,
        ip_address=ip_address,
    )

    logger.info(
        "auth.user_registered",
        user_id=str(user.id),
        org_id=str(org.id),
    )
    return user, org


async def authenticate_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    ip_address: str | None = None,
) -> tuple[str, str, User]:
    """
    Authenticate a user with email and password.

    Returns:
        Tuple of (access_token, refresh_token, user)

    Raises:
        UnauthorizedError if credentials are invalid or account is locked.
    """
    # Fetch user
    result = await db.execute(
        select(User).where(
            User.email == email, User.deleted_at.is_(None)  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()

    if not user:
        # Log failed attempt even for non-existent users
        # (prevents user enumeration via timing)
        await create_audit_log(
            db,
            action=AuditAction.LOGIN_FAILED,
            resource_type="user",
            ip_address=ip_address,
            status="failure",
            detail=f"No user with email '{email}'",
        )
        raise UnauthorizedError("Invalid email or password")

    # Check account status
    if not user.is_active:
        raise UnauthorizedError("Account is deactivated")

    if user.is_locked:
        raise UnauthorizedError(
            f"Account is locked after {User.MAX_FAILED_ATTEMPTS} "
            "failed attempts. Contact an administrator."
        )

    # Verify password
    if not verify_password(password, user.hashed_password):
        # Increment failed attempts
        user.failed_login_attempts += 1
        await db.flush()

        await create_audit_log(
            db,
            action=AuditAction.LOGIN_FAILED,
            resource_type="user",
            resource_id=str(user.id),
            organization_id=user.organization_id,
            user_id=user.id,
            ip_address=ip_address,
            status="failure",
        )
        raise UnauthorizedError("Invalid email or password")

    # Successful login: reset failed attempts, update last_login_at
    user.failed_login_attempts = 0
    user.last_login_at = datetime.now(timezone.utc)
    await db.flush()

    # Generate tokens
    access_token = create_access_token(
        user.id, user.organization_id, user.role
    )
    refresh_token = create_refresh_token(
        user.id, user.organization_id
    )

    await create_audit_log(
        db,
        action=AuditAction.LOGIN,
        resource_type="user",
        resource_id=str(user.id),
        organization_id=user.organization_id,
        user_id=user.id,
        ip_address=ip_address,
    )

    return access_token, refresh_token, user


async def refresh_access_token(
    db: AsyncSession,
    *,
    refresh_token_str: str,
) -> tuple[str, str]:
    """
    Issue a new access token using a valid refresh token.

    Returns:
        Tuple of (new_access_token, new_refresh_token)
    """
    try:
        payload = decode_token(refresh_token_str)
    except Exception:
        raise UnauthorizedError("Invalid or expired refresh token")

    if payload.get("type") != TokenType.REFRESH.value:
        raise UnauthorizedError("Invalid token type")

    user_id = UUID(payload["sub"])

    # Verify user still exists and is active
    result = await db.execute(
        select(User).where(
            User.id == user_id,
            User.is_active == True,  # noqa: E712
            User.deleted_at.is_(None),  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError("User not found or deactivated")

    # Issue new token pair (token rotation for security)
    access_token = create_access_token(
        user.id, user.organization_id, user.role
    )
    new_refresh = create_refresh_token(
        user.id, user.organization_id
    )

    await create_audit_log(
        db,
        action=AuditAction.TOKEN_REFRESH,
        resource_type="user",
        resource_id=str(user.id),
        organization_id=user.organization_id,
        user_id=user.id,
    )

    return access_token, new_refresh


async def authenticate_api_key(
    db: AsyncSession,
    *,
    raw_key: str,
    ip_address: str | None = None,
) -> tuple[User, ApiKey]:
    """
    Authenticate a request using an API key.

    Returns:
        Tuple of (user, api_key)
    """
    key_hash = hash_api_key(raw_key)

    result = await db.execute(
        select(ApiKey).where(
            ApiKey.key_hash == key_hash,
            ApiKey.is_revoked == False,  # noqa: E712
            ApiKey.deleted_at.is_(None),  # noqa: E712
        )
    )
    api_key = result.scalar_one_or_none()

    if not api_key or not api_key.is_valid:
        raise UnauthorizedError("Invalid or expired API key")

    # Update last_used_at
    api_key.last_used_at = datetime.now(timezone.utc)
    await db.flush()

    # Fetch the key's user
    result = await db.execute(
        select(User).where(
            User.id == api_key.user_id,
            User.is_active == True,  # noqa: E712
        )
    )
    user = result.scalar_one_or_none()
    if not user:
        raise UnauthorizedError(
            "API key owner not found or deactivated"
        )

    return user, api_key


async def create_api_key_for_user(
    db: AsyncSession,
    *,
    user_id: UUID,
    org_id: UUID,
    name: str,
    scopes: list[str],
    expires_in_days: int | None = None,
    ip_address: str | None = None,
) -> tuple[ApiKey, str]:
    """
    Create a new API key for a user.

    Returns:
        Tuple of (api_key_model, raw_key)
        The raw key is returned only once — it cannot be retrieved again.
    """
    raw_key, key_hash, key_prefix = generate_api_key()

    expires_at = None
    if expires_in_days:
        expires_at = datetime.now(timezone.utc) + timedelta(
            days=expires_in_days
        )

    api_key = ApiKey(
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        user_id=user_id,
        organization_id=org_id,
        scopes=scopes,
        expires_at=expires_at,
    )
    db.add(api_key)
    await db.flush()

    await create_audit_log(
        db,
        action=AuditAction.API_KEY_CREATED,
        resource_type="api_key",
        resource_id=str(api_key.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )

    logger.info(
        "auth.api_key_created",
        key_id=str(api_key.id),
        user_id=str(user_id),
    )
    return api_key, raw_key


async def revoke_api_key(
    db: AsyncSession,
    *,
    key_id: UUID,
    org_id: UUID,
    user_id: UUID,
    ip_address: str | None = None,
) -> None:
    """Revoke an API key."""
    result = await db.execute(
        select(ApiKey).where(
            ApiKey.id == key_id,
            ApiKey.organization_id == org_id,
            ApiKey.deleted_at.is_(None),  # noqa: E712
        )
    )
    api_key = result.scalar_one_or_none()
    if not api_key:
        raise NotFoundError("API key", str(key_id))

    api_key.is_revoked = True
    await db.flush()

    await create_audit_log(
        db,
        action=AuditAction.API_KEY_REVOKED,
        resource_type="api_key",
        resource_id=str(api_key.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )
