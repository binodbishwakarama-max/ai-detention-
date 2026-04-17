"""
WorkerResult repository — data access for per-worker outcomes.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.worker_result import WorkerResult, WorkerStatus
from src.repositories.base_repository import BaseRepository


class WorkerResultRepository(BaseRepository[WorkerResult]):
    """Repository for WorkerResult CRUD and status tracking."""

    def __init__(self):
        super().__init__(WorkerResult)

    async def get_by_run(
        self,
        db: AsyncSession,
        run_id: UUID,
        org_id: UUID,
    ) -> list[WorkerResult]:
        """Get all worker results for a run."""
        stmt = (
            select(WorkerResult)
            .where(
                WorkerResult.evaluation_run_id == run_id,
                WorkerResult.organization_id == org_id,
                WorkerResult.deleted_at.is_(None),
            )
            .order_by(WorkerResult.created_at)
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_status(
        self,
        db: AsyncSession,
        run_id: UUID,
    ) -> dict[str, int]:
        """Count workers by status for a run."""
        stmt = (
            select(WorkerResult.status, func.count().label("count"))
            .where(
                WorkerResult.evaluation_run_id == run_id,
                WorkerResult.deleted_at.is_(None),
            )
            .group_by(WorkerResult.status)
        )
        result = await db.execute(stmt)
        return {row.status.value: row.count for row in result.all()}

    async def all_workers_completed(
        self,
        db: AsyncSession,
        run_id: UUID,
    ) -> bool:
        """Check if all workers for a run have completed (or failed)."""
        stmt = (
            select(func.count())
            .select_from(WorkerResult)
            .where(
                WorkerResult.evaluation_run_id == run_id,
                WorkerResult.status.in_([WorkerStatus.PENDING, WorkerStatus.RUNNING]),
                WorkerResult.deleted_at.is_(None),
            )
        )
        in_progress = (await db.execute(stmt)).scalar() or 0
        return in_progress == 0

    async def get_avg_processing_time(
        self,
        db: AsyncSession,
        run_id: UUID,
    ) -> float:
        """Get average worker processing time in milliseconds."""
        stmt = (
            select(func.avg(WorkerResult.processing_time_ms))
            .where(
                WorkerResult.evaluation_run_id == run_id,
                WorkerResult.status == WorkerStatus.COMPLETED,
                WorkerResult.deleted_at.is_(None),
            )
        )
        return float((await db.execute(stmt)).scalar() or 0)


# Singleton instance
worker_result_repo = WorkerResultRepository()
