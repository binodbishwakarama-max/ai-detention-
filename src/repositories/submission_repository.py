"""
Submission repository — data access for submissions.

Uses selectinload to batch-load evaluation_runs when needed,
preventing N+1 query patterns.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.models.submission import Submission, SubmissionStatus
from src.repositories.base_repository import BaseRepository
from src.repositories.submission_cache import invalidate_org_submissions


class SubmissionRepository(BaseRepository[Submission]):
    """Repository for Submission CRUD and domain-specific queries."""

    def __init__(self):
        super().__init__(Submission)

    async def create(self, db: AsyncSession, entity: Submission) -> Submission:
        """Override create to invalidate submission cache."""
        created = await super().create(db, entity)
        await invalidate_org_submissions(entity.organization_id)
        return created

    async def create_many(self, db: AsyncSession, entities: list[Submission]) -> list[Submission]:
        """Override create_many to invalidate submission cache."""
        created = await super().create_many(db, entities)
        org_ids = {e.organization_id for e in entities}
        for org_id in org_ids:
            await invalidate_org_submissions(org_id)
        return created

    async def soft_delete(
        self,
        db: AsyncSession,
        entity_id: UUID,
        *,
        org_id: UUID | None = None,
    ) -> bool:
        """Override soft_delete to invalidate submission cache."""
        deleted = await super().soft_delete(db, entity_id, org_id=org_id)
        if deleted and org_id:
            await invalidate_org_submissions(org_id)
        return deleted

    async def get_with_runs(
        self,
        db: AsyncSession,
        submission_id: UUID,
        org_id: UUID,
    ) -> Submission | None:
        """
        Fetch a submission with all its evaluation runs eagerly loaded.

        Uses selectinload to prevent N+1:
        - 1 query for the submission
        - 1 query for all evaluation_runs (batched via IN clause)
        Total: 2 queries regardless of number of runs.
        """
        stmt = (
            select(Submission)
            .options(selectinload(Submission.evaluation_runs))
            .where(
                Submission.id == submission_id,
                Submission.organization_id == org_id,
                Submission.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_status(
        self,
        db: AsyncSession,
        org_id: UUID,
        status: SubmissionStatus,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Submission], int]:
        """List submissions filtered by status within an org."""
        return await self.list_by_org(
            db,
            org_id,
            page=page,
            page_size=page_size,
            extra_filters=[Submission.status == status],
        )

    async def count_by_status(
        self,
        db: AsyncSession,
        org_id: UUID,
    ) -> dict[str, int]:
        """
        Count submissions grouped by status for dashboard metrics.

        Produces a single query with GROUP BY — no N+1.
        """
        stmt = (
            select(
                Submission.status,
                func.count().label("count"),
            )
            .where(
                Submission.organization_id == org_id,
                Submission.deleted_at.is_(None),
            )
            .group_by(Submission.status)
        )
        result = await db.execute(stmt)
        return {row.status.value: row.count for row in result.all()}

    async def search_by_name(
        self,
        db: AsyncSession,
        org_id: UUID,
        query: str,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[Submission], int]:
        """Search submissions by startup name (case-insensitive LIKE)."""
        pattern = f"%{query}%"
        return await self.list_by_org(
            db,
            org_id,
            page=page,
            page_size=page_size,
            extra_filters=[Submission.startup_name.ilike(pattern)],
        )


# Singleton instance
submission_repo = SubmissionRepository()
