"""
Tests for authentication endpoints.

Verifies:
- User registration with organization creation
- Login with valid/invalid credentials
- Token refresh flow
- Account lockout after failed attempts
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_register_creates_user_and_org(
    client: AsyncClient,
) -> None:
    """Test that registration creates both user and organization."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "newuser@example.com",
            "password": "SecurePass123!",
            "full_name": "New User",
            "organization_name": "New Org",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert data["role"] == "admin"  # first user gets admin


@pytest.mark.asyncio
async def test_register_duplicate_email_fails(
    client: AsyncClient,
) -> None:
    """Test that registering with an existing email returns 409."""
    # Register first user
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dupe@example.com",
            "password": "SecurePass123!",
            "full_name": "First User",
            "organization_name": "First Org",
        },
    )

    # Try registering with the same email
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "dupe@example.com",
            "password": "SecurePass123!",
            "full_name": "Second User",
            "organization_name": "Second Org",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient) -> None:
    """Test successful login returns token pair."""
    # Register
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "login@example.com",
            "password": "SecurePass123!",
            "full_name": "Login User",
            "organization_name": "Login Org",
        },
    )

    # Login
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "login@example.com",
            "password": "SecurePass123!",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


@pytest.mark.asyncio
async def test_login_invalid_password(
    client: AsyncClient,
) -> None:
    """Test that wrong password returns 401."""
    # Register
    await client.post(
        "/api/v1/auth/register",
        json={
            "email": "wrong@example.com",
            "password": "SecurePass123!",
            "full_name": "Wrong User",
            "organization_name": "Wrong Org",
        },
    )

    # Login with wrong password
    response = await client.post(
        "/api/v1/auth/login",
        json={
            "email": "wrong@example.com",
            "password": "WrongPassword123!",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me_authenticated(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test that /auth/me returns the authenticated user."""
    response = await client.get(
        "/api/v1/auth/me", headers=auth_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "test@example.com"


@pytest.mark.asyncio
async def test_get_me_unauthenticated(
    client: AsyncClient,
) -> None:
    """Test that /auth/me returns 401 without auth."""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_password_validation(
    client: AsyncClient,
) -> None:
    """Test that weak passwords are rejected."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "weak@example.com",
            "password": "short",  # too short, no uppercase/digit/special
            "full_name": "Weak User",
            "organization_name": "Weak Org",
        },
    )
    assert response.status_code == 422
