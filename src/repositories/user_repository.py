"""
User repository — data access for authenticated users.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.user import User
from src.repositories.base_repository import BaseRepository


class UserRepository(BaseRepository[User]):
    """Repository for User CRUD and authentication queries."""

    def __init__(self):
        super().__init__(User)

    async def get_by_email(
        self,
        db: AsyncSession,
        email: str,
    ) -> User | None:
        """Fetch a user by email (case-insensitive)."""
        stmt = (
            select(User)
            .where(
                User.email == email.lower(),
                User.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def email_exists(
        self,
        db: AsyncSession,
        email: str,
    ) -> bool:
        """Check if an email is already registered."""
        user = await self.get_by_email(db, email)
        return user is not None

    async def list_by_org(
        self,
        db: AsyncSession,
        org_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        **kwargs,
    ) -> tuple[list[User], int]:
        """List users for an organization."""
        return await super().list_by_org(
            db, org_id, page=page, page_size=page_size, **kwargs
        )

    async def increment_failed_login(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> None:
        """Increment failed login attempts counter."""
        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(failed_login_attempts=User.failed_login_attempts + 1)
        )
        await db.execute(stmt)

    async def reset_failed_login(
        self,
        db: AsyncSession,
        user_id: UUID,
    ) -> None:
        """Reset failed login attempts on successful login."""
        from datetime import datetime, timezone

        stmt = (
            update(User)
            .where(User.id == user_id)
            .values(
                failed_login_attempts=0,
                last_login_at=datetime.now(timezone.utc),
            )
        )
        await db.execute(stmt)


# Singleton instance
user_repo = UserRepository()
