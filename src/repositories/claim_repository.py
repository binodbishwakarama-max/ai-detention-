"""
Claim repository — data access for extracted claims.

Provides bulk-insert for worker output (hundreds of claims per run)
and analytics queries with efficient indexing.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.claim import Claim
from src.repositories.base_repository import BaseRepository


class ClaimRepository(BaseRepository[Claim]):
    """Repository for Claim CRUD and analytics."""

    def __init__(self):
        super().__init__(Claim)

    async def bulk_create(
        self,
        db: AsyncSession,
        claims: list[Claim],
    ) -> list[Claim]:
        """
        Bulk-insert claims from a worker's output.

        Uses add_all + single flush for efficiency — one round-trip
        instead of N round-trips for N claims.
        """
        return await self.create_many(db, claims)

    async def get_by_run(
        self,
        db: AsyncSession,
        run_id: UUID,
        org_id: UUID,
        *,
        page: int = 1,
        page_size: int = 50,
        category: str | None = None,
    ) -> tuple[list[Claim], int]:
        """Get claims for a run, optionally filtered by category."""
        filters = [Claim.evaluation_run_id == run_id]
        if category:
            filters.append(Claim.category == category)

        return await self.list_by_org(
            db, org_id, page=page, page_size=page_size,
            extra_filters=filters,
            order_by=Claim.confidence_score.desc(),
        )

    async def count_by_category(
        self,
        db: AsyncSession,
        run_id: UUID,
        org_id: UUID,
    ) -> dict[str, int]:
        """Count claims grouped by category for a specific run."""
        stmt = (
            select(Claim.category, func.count().label("count"))
            .where(
                Claim.evaluation_run_id == run_id,
                Claim.organization_id == org_id,
                Claim.deleted_at.is_(None),
            )
            .group_by(Claim.category)
        )
        result = await db.execute(stmt)
        return {row.category: row.count for row in result.all()}

    async def count_by_verification_status(
        self,
        db: AsyncSession,
        run_id: UUID,
        org_id: UUID,
    ) -> dict[str, int]:
        """Count claims grouped by verification status."""
        stmt = (
            select(Claim.verification_status, func.count().label("count"))
            .where(
                Claim.evaluation_run_id == run_id,
                Claim.organization_id == org_id,
                Claim.deleted_at.is_(None),
            )
            .group_by(Claim.verification_status)
        )
        result = await db.execute(stmt)
        return {row.verification_status: row.count for row in result.all()}

    async def get_high_confidence_claims(
        self,
        db: AsyncSession,
        run_id: UUID,
        org_id: UUID,
        threshold: float = 0.8,
    ) -> list[Claim]:
        """Get claims with confidence above threshold (no pagination — used for scoring)."""
        stmt = (
            select(Claim)
            .where(
                Claim.evaluation_run_id == run_id,
                Claim.organization_id == org_id,
                Claim.confidence_score >= threshold,
                Claim.deleted_at.is_(None),
            )
            .order_by(Claim.confidence_score.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


# Singleton instance
claim_repo = ClaimRepository()
