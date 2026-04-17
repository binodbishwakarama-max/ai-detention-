"""
Result service — query and export pipeline outputs.

Results are aggregated from WorkerResult, Claim, Contradiction, and Score
models. The legacy EvaluationResult table has been removed.
"""

from __future__ import annotations

from uuid import UUID

import orjson
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.error_handler import NotFoundError
from src.models.claim import Claim
from src.models.contradiction import Contradiction
from src.models.evaluation import EvaluationRun
from src.models.score import Score
from src.models.worker_result import WorkerResult, WorkerStatus
from src.services.storage_service import upload_export_data

logger = structlog.get_logger(__name__)


async def get_worker_results_for_run(
    db: AsyncSession,
    *,
    run_id: UUID,
    org_id: UUID,
) -> list[WorkerResult]:
    """Fetch all worker results for a specific evaluation run."""
    # Verify run exists and belongs to org
    await _verify_run(db, run_id, org_id)

    stmt = (
        select(WorkerResult)
        .where(
            WorkerResult.evaluation_run_id == run_id,
            WorkerResult.deleted_at.is_(None),
        )
        .order_by(WorkerResult.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_claims_for_run(
    db: AsyncSession,
    *,
    run_id: UUID,
    org_id: UUID,
    category: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Claim], int]:
    """Fetch paginated claims for a specific evaluation run."""
    await _verify_run(db, run_id, org_id)

    base_where = [
        Claim.evaluation_run_id == run_id,
        Claim.organization_id == org_id,
        Claim.deleted_at.is_(None),
    ]
    if category:
        base_where.append(Claim.category == category)

    count_stmt = (
        select(func.count())
        .select_from(Claim)
        .where(*base_where)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Claim)
        .where(*base_where)
        .order_by(Claim.created_at)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    claims = list(result.scalars().all())

    return claims, total


async def get_contradictions_for_run(
    db: AsyncSession,
    *,
    run_id: UUID,
    org_id: UUID,
) -> list[Contradiction]:
    """Fetch all contradictions for a specific evaluation run."""
    await _verify_run(db, run_id, org_id)

    stmt = (
        select(Contradiction)
        .where(
            Contradiction.evaluation_run_id == run_id,
            Contradiction.organization_id == org_id,
            Contradiction.deleted_at.is_(None),
        )
        .order_by(Contradiction.severity.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_scores_for_run(
    db: AsyncSession,
    *,
    run_id: UUID,
    org_id: UUID,
) -> list[Score]:
    """Fetch all scores for a specific evaluation run."""
    await _verify_run(db, run_id, org_id)

    stmt = (
        select(Score)
        .where(
            Score.evaluation_run_id == run_id,
            Score.organization_id == org_id,
            Score.deleted_at.is_(None),
        )
        .order_by(Score.dimension)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_results_summary(
    db: AsyncSession,
    *,
    run_id: UUID,
    org_id: UUID,
) -> dict:
    """
    Compute aggregate summary of all pipeline outputs for a run.

    Returns worker counts, claim/contradiction totals, scores, and overall score.
    """
    run = await _verify_run(db, run_id, org_id)

    # Count claims
    claim_count = (await db.execute(
        select(func.count())
        .select_from(Claim)
        .where(
            Claim.evaluation_run_id == run_id,
            Claim.deleted_at.is_(None),
        )
    )).scalar() or 0

    # Count contradictions
    contradiction_count = (await db.execute(
        select(func.count())
        .select_from(Contradiction)
        .where(
            Contradiction.evaluation_run_id == run_id,
            Contradiction.deleted_at.is_(None),
        )
    )).scalar() or 0

    # Get scores
    scores = await get_scores_for_run(db, run_id=run_id, org_id=org_id)

    return {
        "run_id": str(run_id),
        "status": run.status.value,
        "overall_score": run.overall_score,
        "total_workers": run.total_workers,
        "completed_workers": run.completed_workers,
        "failed_workers": run.failed_workers,
        "total_claims": claim_count,
        "total_contradictions": contradiction_count,
        "scores": scores,
        "progress_pct": run.progress_pct,
    }


async def export_results(
    db: AsyncSession,
    *,
    run_id: UUID,
    org_id: UUID,
    fmt: str = "json",
) -> str:
    """
    Export all pipeline results for a run to S3.

    Aggregates worker results, claims, contradictions, and scores
    into a single export file.
    """
    run = await _verify_run(db, run_id, org_id)

    # Gather all data
    workers = await get_worker_results_for_run(db, run_id=run_id, org_id=org_id)
    claims, _ = await get_claims_for_run(db, run_id=run_id, org_id=org_id, page_size=10000)
    contradictions = await get_contradictions_for_run(db, run_id=run_id, org_id=org_id)
    scores = await get_scores_for_run(db, run_id=run_id, org_id=org_id)

    export_payload = {
        "run_id": str(run_id),
        "status": run.status.value,
        "overall_score": run.overall_score,
        "workers": [
            {
                "worker_type": w.worker_type,
                "status": w.status.value,
                "processing_time_ms": w.processing_time_ms,
                "output_data": w.output_data,
                "error_message": w.error_message,
            }
            for w in workers
        ],
        "claims": [
            {
                "claim_text": c.claim_text,
                "category": c.category,
                "confidence_score": c.confidence_score,
                "verification_status": c.verification_status,
                "source_reference": c.source_reference,
            }
            for c in claims
        ],
        "contradictions": [
            {
                "contradiction_type": ct.contradiction_type,
                "severity": ct.severity,
                "explanation": ct.explanation,
            }
            for ct in contradictions
        ],
        "scores": [
            {
                "dimension": s.dimension,
                "value": s.value,
                "weight": s.weight,
                "rationale": s.rationale,
            }
            for s in scores
        ],
    }

    if fmt == "json":
        export_data = orjson.dumps(export_payload, option=orjson.OPT_INDENT_2)
    elif fmt == "csv":
        import csv
        import io

        output = io.StringIO()
        writer = csv.DictWriter(
            output,
            fieldnames=["dimension", "value", "weight", "rationale"],
        )
        writer.writeheader()
        for s in scores:
            writer.writerow({
                "dimension": s.dimension,
                "value": s.value,
                "weight": s.weight,
                "rationale": s.rationale,
            })
        export_data = output.getvalue().encode("utf-8")
    else:
        export_data = orjson.dumps(export_payload)

    upload_export_data(org_id, run_id, export_data, fmt)

    from src.services.storage_service import get_export_download_url
    download_url = get_export_download_url(org_id, run_id, fmt)

    logger.info(
        "results.exported",
        run_id=str(run_id),
        format=fmt,
        claims=len(claims),
        scores=len(scores),
    )
    return download_url


async def _verify_run(
    db: AsyncSession, run_id: UUID, org_id: UUID
) -> EvaluationRun:
    """Verify a run exists and belongs to the given org."""
    result = await db.execute(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id,
            EvaluationRun.organization_id == org_id,
            EvaluationRun.deleted_at.is_(None),  # noqa: E712
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise NotFoundError("Evaluation run", str(run_id))
    return run
