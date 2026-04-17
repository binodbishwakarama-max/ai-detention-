"""
Contradiction repository — data access for claim conflicts.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.contradiction import Contradiction
from src.repositories.base_repository import BaseRepository


class ContradictionRepository(BaseRepository[Contradiction]):
    """Repository for Contradiction CRUD and analytics."""

    def __init__(self):
        super().__init__(Contradiction)

    async def get_with_claims(
        self,
        db: AsyncSession,
        contradiction_id: UUID,
        org_id: UUID,
    ) -> Contradiction | None:
        """
        Fetch a contradiction with both claims eagerly loaded.

        Uses joinedload for claim_a and claim_b since they're
        single-entity relations (not collections).
        """
        from sqlalchemy.orm import joinedload

        stmt = (
            select(Contradiction)
            .options(
                joinedload(Contradiction.claim_a),
                joinedload(Contradiction.claim_b),
            )
            .where(
                Contradiction.id == contradiction_id,
                Contradiction.organization_id == org_id,
                Contradiction.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        return result.unique().scalar_one_or_none()

    async def get_by_run_with_claims(
        self,
        db: AsyncSession,
        run_id: UUID,
        org_id: UUID,
    ) -> list[Contradiction]:
        """
        Get all contradictions for a run with claims eagerly loaded.

        Uses selectinload: 1 query for contradictions + 2 for claims.
        """
        from sqlalchemy.orm import joinedload

        stmt = (
            select(Contradiction)
            .options(
                joinedload(Contradiction.claim_a),
                joinedload(Contradiction.claim_b),
            )
            .where(
                Contradiction.evaluation_run_id == run_id,
                Contradiction.organization_id == org_id,
                Contradiction.deleted_at.is_(None),
            )
            .order_by(Contradiction.severity.desc())
        )
        result = await db.execute(stmt)
        return list(result.unique().scalars().all())

    async def count_by_severity_bucket(
        self,
        db: AsyncSession,
        run_id: UUID,
        org_id: UUID,
    ) -> dict[str, int]:
        """
        Count contradictions grouped by severity bucket.

        Buckets: critical (>0.8), high (0.6-0.8), medium (0.4-0.6), low (<0.4)
        """
        from sqlalchemy import case

        severity_bucket = case(
            (Contradiction.severity > 0.8, "critical"),
            (Contradiction.severity > 0.6, "high"),
            (Contradiction.severity > 0.4, "medium"),
            else_="low",
        ).label("bucket")

        stmt = (
            select(severity_bucket, func.count().label("count"))
            .where(
                Contradiction.evaluation_run_id == run_id,
                Contradiction.organization_id == org_id,
                Contradiction.deleted_at.is_(None),
            )
            .group_by(severity_bucket)
        )
        result = await db.execute(stmt)
        return {row.bucket: row.count for row in result.all()}


# Singleton instance
contradiction_repo = ContradictionRepository()
