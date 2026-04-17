"""
Authentication and authorization module.

Supports two authentication methods:
1. JWT tokens — for interactive users (web UI, CLI)
2. API keys — for programmatic access (CI/CD, integrations)

Security design:
- Passwords: bcrypt with automatic salt (work factor 12)
- JWT: HS256 with configurable expiry, includes org_id for tenant isolation
- API keys: SHA-256 hashed, only the prefix is stored in plaintext for display
- RBAC: three roles (ADMIN, MEMBER, VIEWER) with hierarchical permissions
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import UUID

from jose import jwt
from passlib.context import CryptContext

from src.config import get_settings

# ── Password Hashing ────────────────────────────────────────
# bcrypt with work factor 12 (~250ms per hash on modern hardware).
# Auto-migration from deprecated schemes via "deprecated='auto'".
pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=12,
)


class Role(str, Enum):
    """User roles with hierarchical permissions."""

    ADMIN = "admin"  # full access, manage org settings and users
    MEMBER = "member"  # create/run evaluations, manage datasets
    VIEWER = "viewer"  # read-only access to results and metrics


class TokenType(str, Enum):
    """JWT token types."""

    ACCESS = "access"
    REFRESH = "refresh"


# ── Role Hierarchy ──────────────────────────────────────────
# Higher number = more permissions. Used for "at least" checks.
ROLE_HIERARCHY: dict[Role, int] = {
    Role.VIEWER: 1,
    Role.MEMBER: 2,
    Role.ADMIN: 3,
}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against its bcrypt hash."""
    return pwd_context.verify(plain_password, hashed_password)


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt."""
    return pwd_context.hash(password)


def create_access_token(
    user_id: UUID,
    org_id: UUID,
    role: Role,
    expires_delta: timedelta | None = None,
) -> str:
    """
    Create a JWT access token.

    The token payload includes:
    - sub: user ID (standard JWT claim)
    - org: organization ID (for tenant isolation in every query)
    - role: user role (for authorization checks)
    - type: token type (to prevent refresh tokens from being used as access tokens)
    - exp: expiration timestamp
    - iat: issued-at timestamp
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.jwt_access_token_expire_minutes)
    )
    payload = {
        "jti": str(uuid.uuid4()),
        "sub": str(user_id),
        "org": str(org_id),
        "role": role.value,
        "type": TokenType.ACCESS.value,
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(user_id: UUID, org_id: UUID) -> str:
    """
    Create a JWT refresh token.

    Refresh tokens have a longer lifespan and contain minimal claims.
    They can only be used to obtain new access tokens, not to access resources.
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=settings.jwt_refresh_token_expire_days)
    payload = {
        "sub": str(user_id),
        "org": str(org_id),
        "type": TokenType.REFRESH.value,
        "exp": expire,
        "iat": now,
    }
    return jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """
    Decode and validate a JWT token.

    Raises JWTError if the token is invalid, expired, or tampered with.
    The caller is responsible for checking the token type.
    """
    settings = get_settings()
    return jwt.decode(
        token, settings.secret_key, algorithms=[settings.jwt_algorithm]
    )


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        Tuple of (raw_key, key_hash, key_prefix)

    The raw key is returned to the user exactly once. We store only:
    - key_hash: SHA-256 hash for authentication lookups
    - key_prefix: first 11 chars for display in the UI (e.g., "ev_dk3n...")

    Format: "ev_{40 random hex chars}" — 160 bits of entropy.
    """
    raw = f"ev_{secrets.token_hex(20)}"
    key_hash = hashlib.sha256(raw.encode()).hexdigest()
    key_prefix = raw[:11]  # "ev_" + first 8 chars
    return raw, key_hash, key_prefix


def hash_api_key(raw_key: str) -> str:
    """Hash an API key for comparison during authentication."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def has_permission(user_role: Role, required_role: Role) -> bool:
    """
    Check if a user's role meets the minimum required role.

    Uses hierarchical comparison: ADMIN > MEMBER > VIEWER.
    An ADMIN can do everything a MEMBER can, and so on.
    """
    return ROLE_HIERARCHY.get(user_role, 0) >= ROLE_HIERARCHY.get(required_role, 0)


# ── JWT Blacklist Caching ───────────────────────────────────
from src.cache import cache_manager

async def blacklist_token(token: str) -> None:
    """Add a token's JTI to the blacklist until its formal expiration."""
    try:
        payload = decode_token(token)
        jti = payload.get("jti")
        exp = payload.get("exp")
        if jti and exp:
            ttl = max(1, int(exp - datetime.now(timezone.utc).timestamp()))
            await cache_manager.set(f"blacklist:{jti}", "1", ttl=ttl)
    except Exception:
        pass  # If decode fails, it's already invalid

async def is_token_blacklisted(jti: str) -> bool:
    """Check if a token JTI is blacklisted returning False if Cache falls open."""
    if not cache_manager.is_healthy:
        return False
    result = await cache_manager.get(f"blacklist:{jti}")
    return result is not None
