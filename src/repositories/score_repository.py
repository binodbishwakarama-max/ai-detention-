"""
Score repository — data access for immutable scores.

IMMUTABILITY ENFORCEMENT:
- create() is the only write method exposed
- No update/patch method exists
- soft_delete is overridden to raise an error
- The database trigger (see migration) also prevents UPDATE/DELETE
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.error_handler import ConflictError
from src.models.score import Score
from src.repositories.base_repository import BaseRepository


class ScoreRepository(BaseRepository[Score]):
    """
    Repository for Score — IMMUTABLE after creation.

    Scores cannot be updated or deleted once written. To re-score
    a submission, create a new evaluation run.
    """

    def __init__(self):
        super().__init__(Score)

    async def create_score(
        self,
        db: AsyncSession,
        score: Score,
    ) -> Score:
        """
        Create an immutable score. Checks uniqueness of (run_id, dimension).

        Raises ConflictError if a score for this dimension already exists
        in the run — enforced at both application and database level.
        """
        existing = await self._find_by_run_and_dimension(
            db, score.evaluation_run_id, score.dimension, score.organization_id
        )
        if existing:
            raise ConflictError(
                f"Score for dimension '{score.dimension}' already exists "
                f"in run {score.evaluation_run_id}. Scores are immutable."
            )
        return await self.create(db, score)

    async def bulk_create_scores(
        self,
        db: AsyncSession,
        scores: list[Score],
    ) -> list[Score]:
        """Bulk-insert multiple scores for a run (one per dimension)."""
        # Validate no duplicates in the batch
        dimensions = [s.dimension for s in scores]
        if len(dimensions) != len(set(dimensions)):
            raise ConflictError("Duplicate dimensions in score batch")
        return await self.create_many(db, scores)

    async def soft_delete(self, *args, **kwargs) -> bool:
        """Scores are immutable — deletion is not permitted."""
        raise ConflictError(
            "Scores are immutable and cannot be deleted. "
            "Create a new evaluation run to re-score."
        )

    async def get_scores_for_run(
        self,
        db: AsyncSession,
        run_id: UUID,
        org_id: UUID,
    ) -> list[Score]:
        """Get all scores for an evaluation run, ordered by weight descending."""
        stmt = (
            select(Score)
            .where(
                Score.evaluation_run_id == run_id,
                Score.organization_id == org_id,
                Score.deleted_at.is_(None),
            )
            .order_by(Score.weight.desc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def compute_weighted_average(
        self,
        db: AsyncSession,
        run_id: UUID,
        org_id: UUID,
    ) -> float | None:
        """
        Compute the weighted average score for a run.

        Formula: Σ(value × weight) / Σ(weight)

        Returns None if no scores exist.
        This is a single-query aggregation — no N+1.
        """
        stmt = select(
            func.sum(Score.value * Score.weight).label("weighted_sum"),
            func.sum(Score.weight).label("total_weight"),
        ).where(
            Score.evaluation_run_id == run_id,
            Score.organization_id == org_id,
            Score.deleted_at.is_(None),
        )
        result = await db.execute(stmt)
        row = result.one()

        if row.total_weight is None or row.total_weight == 0:
            return None
        return round(float(row.weighted_sum / row.total_weight), 4)

    async def get_dimension_averages_across_org(
        self,
        db: AsyncSession,
        org_id: UUID,
    ) -> dict[str, float]:
        """
        Get average scores per dimension across all runs in an org.

        Used for benchmarking: "how does this submission compare to org average?"
        """
        stmt = (
            select(
                Score.dimension,
                func.avg(Score.value).label("avg_value"),
            )
            .where(
                Score.organization_id == org_id,
                Score.deleted_at.is_(None),
            )
            .group_by(Score.dimension)
        )
        result = await db.execute(stmt)
        return {row.dimension: round(float(row.avg_value), 4) for row in result.all()}

    async def _find_by_run_and_dimension(
        self,
        db: AsyncSession,
        run_id: UUID,
        dimension: str,
        org_id: UUID,
    ) -> Score | None:
        """Internal: check if a score exists for a run+dimension pair."""
        stmt = (
            select(Score)
            .where(
                Score.evaluation_run_id == run_id,
                Score.dimension == dimension,
                Score.organization_id == org_id,
                Score.deleted_at.is_(None),
            )
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()


# Singleton instance
score_repo = ScoreRepository()
