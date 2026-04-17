"""
EvaluationRun repository — data access with optimistic locking.

Optimistic locking pattern:
  1. Read the current version from the database
  2. Apply business logic
  3. UPDATE ... WHERE id=X AND version=Y SET version=Y+1
  4. If rowcount == 0 → concurrent modification detected → raise ConflictError

This avoids pessimistic locks (SELECT FOR UPDATE) which reduce throughput
under high concurrency.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.middleware.error_handler import ConflictError, NotFoundError
from src.models.evaluation import EvaluationRun, RunStatus
from src.repositories.base_repository import BaseRepository


class EvaluationRunRepository(BaseRepository[EvaluationRun]):
    """Repository for EvaluationRun with optimistic locking support."""

    def __init__(self):
        super().__init__(EvaluationRun)

    async def get_with_all_relations(
        self,
        db: AsyncSession,
        run_id: UUID,
        org_id: UUID,
    ) -> EvaluationRun | None:
        """
        Fetch a run with ALL relations eagerly loaded.

        Uses selectinload (not joinedload) to avoid Cartesian products
        when loading multiple one-to-many relations. This produces:
        - 1 query for the run
        - 1 query for worker_results (IN clause)
        - 1 query for claims (IN clause)
        - 1 query for contradictions (IN clause)
        - 1 query for scores (IN clause)
        Total: 5 queries, linear O(n), never N+1.
        """
        stmt = (
            select(EvaluationRun)
            .options(
                selectinload(EvaluationRun.worker_results),
                selectinload(EvaluationRun.claims),
                selectinload(EvaluationRun.contradictions),
                selectinload(EvaluationRun.scores),
            )
            .where(
                EvaluationRun.id == run_id,
                EvaluationRun.organization_id == org_id,
                EvaluationRun.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_with_optimistic_lock(
        self,
        db: AsyncSession,
        run_id: UUID,
        expected_version: int,
        **values: dict,
    ) -> EvaluationRun:
        """
        Update a run with optimistic locking.

        Atomically checks that the version matches expected_version and
        increments it. If another writer modified the row concurrently,
        the WHERE clause won't match and we raise ConflictError.

        This is the ONLY method that should be used to update evaluation runs.
        """
        stmt = (
            update(EvaluationRun)
            .where(
                EvaluationRun.id == run_id,
                EvaluationRun.version == expected_version,
                EvaluationRun.deleted_at.is_(None),
            )
            .values(
                version=expected_version + 1,
                updated_at=datetime.now(timezone.utc),
                **values,
            )
            .returning(EvaluationRun)
        )
        result = await db.execute(stmt)
        row = result.scalar_one_or_none()

        if row is None:
            # Check if the entity exists at all
            exists = await self.exists(db, run_id)
            if not exists:
                raise NotFoundError("Evaluation run", str(run_id))
            raise ConflictError(
                f"Concurrent modification detected on evaluation run {run_id}. "
                f"Expected version {expected_version} but it has been updated. "
                f"Retry your operation."
            )

        return row

    async def transition_status(
        self,
        db: AsyncSession,
        run_id: UUID,
        expected_version: int,
        new_status: RunStatus,
        **extra_values,
    ) -> EvaluationRun:
        """
        Transition a run to a new status with optimistic locking.

        Convenience wrapper around update_with_optimistic_lock for
        state machine transitions.
        """
        values = {"status": new_status, **extra_values}

        if new_status == RunStatus.RUNNING:
            values["started_at"] = datetime.now(timezone.utc)
        elif new_status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED):
            values["completed_at"] = datetime.now(timezone.utc)

        return await self.update_with_optimistic_lock(
            db, run_id, expected_version, **values
        )

    async def list_active_by_org(
        self,
        db: AsyncSession,
        org_id: UUID,
    ) -> list[EvaluationRun]:
        """List all active (non-terminal) runs for an organization."""
        stmt = (
            select(EvaluationRun)
            .where(
                EvaluationRun.organization_id == org_id,
                EvaluationRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING]),
                EvaluationRun.deleted_at.is_(None),
            )
            .order_by(EvaluationRun.created_at.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def count_active_by_org(
        self,
        db: AsyncSession,
        org_id: UUID,
    ) -> int:
        """Count active (pending/running) runs for concurrency limiting."""
        stmt = (
            select(func.count())
            .select_from(EvaluationRun)
            .where(
                EvaluationRun.organization_id == org_id,
                EvaluationRun.status.in_([RunStatus.PENDING, RunStatus.RUNNING]),
                EvaluationRun.deleted_at.is_(None),
            )
        )
        return (await db.execute(stmt)).scalar() or 0

    async def get_runs_for_submission(
        self,
        db: AsyncSession,
        submission_id: UUID,
        org_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[EvaluationRun], int]:
        """List all runs for a specific submission."""
        return await self.list_by_org(
            db,
            org_id,
            page=page,
            page_size=page_size,
            extra_filters=[EvaluationRun.submission_id == submission_id],
        )

    async def get_latest_completed_run(
        self,
        db: AsyncSession,
        submission_id: UUID,
        org_id: UUID,
    ) -> EvaluationRun | None:
        """Get the most recently completed run for a submission."""
        stmt = (
            select(EvaluationRun)
            .where(
                EvaluationRun.submission_id == submission_id,
                EvaluationRun.organization_id == org_id,
                EvaluationRun.status == RunStatus.COMPLETED,
                EvaluationRun.deleted_at.is_(None),
            )
            .order_by(EvaluationRun.completed_at.desc())
            .limit(1)
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


# Singleton instance
evaluation_run_repo = EvaluationRunRepository()
