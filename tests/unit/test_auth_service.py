"""Unit tests for authentication service."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.error_handler import ConflictError, UnauthorizedError
from src.security import Role
from src.services.auth_service import (
    authenticate_user,
    create_api_key_for_user,
    refresh_access_token,
    register_user,
    revoke_api_key,
)
from tests.factories import create_organization, create_user


@pytest.mark.asyncio
class TestRegisterUser:
    async def test_register_creates_user_and_org(self, db_session: AsyncSession):
        user, org = await register_user(
            db_session,
            email="new@test.com",
            password="SecurePass123!",
            full_name="New User",
            organization_name="New Org",
        )
        assert user.email == "new@test.com"
        assert user.role == Role.ADMIN
        assert org.name == "New Org"
        assert user.organization_id == org.id

    async def test_register_duplicate_email_raises_conflict(
        self, db_session: AsyncSession
    ):
        await register_user(
            db_session,
            email="dupe@test.com",
            password="SecurePass123!",
            full_name="First",
            organization_name="Org-A",
        )
        with pytest.raises(ConflictError, match="already exists"):
            await register_user(
                db_session,
                email="dupe@test.com",
                password="SecurePass123!",
                full_name="Second",
                organization_name="Org-B",
            )

    async def test_register_duplicate_org_slug_raises_conflict(
        self, db_session: AsyncSession
    ):
        await register_user(
            db_session,
            email="a@test.com",
            password="SecurePass123!",
            full_name="A",
            organization_name="Same Org",
        )
        with pytest.raises(ConflictError, match="already exists"):
            await register_user(
                db_session,
                email="b@test.com",
                password="SecurePass123!",
                full_name="B",
                organization_name="Same Org",
            )


@pytest.mark.asyncio
class TestAuthenticateUser:
    async def test_valid_credentials_returns_tokens(
        self, db_session: AsyncSession
    ):
        await register_user(
            db_session,
            email="login@test.com",
            password="SecurePass123!",
            full_name="Login",
            organization_name="Login Org",
        )
        access, refresh, user = await authenticate_user(
            db_session, email="login@test.com", password="SecurePass123!"
        )
        assert access
        assert refresh
        assert user.email == "login@test.com"
        assert user.failed_login_attempts == 0

    async def test_wrong_password_raises_unauthorized(
        self, db_session: AsyncSession
    ):
        await register_user(
            db_session,
            email="wrong@test.com",
            password="SecurePass123!",
            full_name="Wrong",
            organization_name="Wrong Org",
        )
        with pytest.raises(UnauthorizedError, match="Invalid"):
            await authenticate_user(
                db_session, email="wrong@test.com", password="BadPass!"
            )

    async def test_nonexistent_email_raises_unauthorized(
        self, db_session: AsyncSession
    ):
        with pytest.raises(UnauthorizedError, match="Invalid"):
            await authenticate_user(
                db_session, email="ghost@test.com", password="Any123!"
            )

    async def test_deactivated_user_raises_unauthorized(
        self, db_session: AsyncSession
    ):
        user, _ = await register_user(
            db_session,
            email="deactivated@test.com",
            password="SecurePass123!",
            full_name="Deactivated",
            organization_name="Deact Org",
        )
        user.is_active = False
        await db_session.flush()

        with pytest.raises(UnauthorizedError, match="deactivated"):
            await authenticate_user(
                db_session,
                email="deactivated@test.com",
                password="SecurePass123!",
            )

    async def test_failed_login_increments_counter(
        self, db_session: AsyncSession
    ):
        await register_user(
            db_session,
            email="counter@test.com",
            password="SecurePass123!",
            full_name="Counter",
            organization_name="Counter Org",
        )
        for _ in range(3):
            with pytest.raises(UnauthorizedError):
                await authenticate_user(
                    db_session,
                    email="counter@test.com",
                    password="WrongPass!",
                )


@pytest.mark.asyncio
class TestRefreshToken:
    async def test_valid_refresh_returns_new_tokens(
        self, db_session: AsyncSession
    ):
        await register_user(
            db_session,
            email="refresh@test.com",
            password="SecurePass123!",
            full_name="Refresh",
            organization_name="Refresh Org",
        )
        _, refresh, _ = await authenticate_user(
            db_session,
            email="refresh@test.com",
            password="SecurePass123!",
        )
        new_access, new_refresh = await refresh_access_token(
            db_session, refresh_token_str=refresh
        )
        assert new_access
        assert new_refresh
        assert new_access != new_refresh

    async def test_invalid_refresh_token_raises(
        self, db_session: AsyncSession
    ):
        with pytest.raises(UnauthorizedError):
            await refresh_access_token(
                db_session, refresh_token_str="invalid.token.here"
            )

    async def test_access_token_as_refresh_raises(
        self, db_session: AsyncSession
    ):
        await register_user(
            db_session,
            email="mixup@test.com",
            password="SecurePass123!",
            full_name="Mixup",
            organization_name="Mixup Org",
        )
        access, _, _ = await authenticate_user(
            db_session,
            email="mixup@test.com",
            password="SecurePass123!",
        )
        with pytest.raises(UnauthorizedError, match="token type"):
            await refresh_access_token(
                db_session, refresh_token_str=access
            )


@pytest.mark.asyncio
class TestApiKeys:
    async def test_create_api_key(self, db_session: AsyncSession):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)

        api_key, raw = await create_api_key_for_user(
            db_session,
            user_id=user.id,
            org_id=org.id,
            name="Test Key",
            scopes=["evaluations:read"],
        )
        assert api_key.name == "Test Key"
        assert raw.startswith("ev_")
        assert api_key.key_prefix == raw[:11]

    async def test_revoke_api_key(self, db_session: AsyncSession):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)

        api_key, _ = await create_api_key_for_user(
            db_session,
            user_id=user.id,
            org_id=org.id,
            name="Revoke Key",
            scopes=["evaluations:read"],
        )
        await revoke_api_key(
            db_session,
            key_id=api_key.id,
            org_id=org.id,
            user_id=user.id,
        )
        assert api_key.is_revoked is True
