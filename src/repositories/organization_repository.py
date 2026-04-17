"""
Organization repository — data access for multi-tenant root entity.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.organization import Organization
from src.repositories.base_repository import BaseRepository


class OrganizationRepository(BaseRepository[Organization]):
    """Repository for Organization CRUD."""

    def __init__(self):
        super().__init__(Organization)

    async def get_by_slug(
        self,
        db: AsyncSession,
        slug: str,
    ) -> Organization | None:
        """Fetch an organization by its URL-safe slug."""
        stmt = (
            select(Organization)
            .where(
                Organization.slug == slug,
                Organization.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def slug_exists(
        self,
        db: AsyncSession,
        slug: str,
    ) -> bool:
        """Check if an organization slug is already taken."""
        org = await self.get_by_slug(db, slug)
        return org is not None


# Singleton instance
organization_repo = OrganizationRepository()
