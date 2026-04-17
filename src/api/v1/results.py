"""
Result endpoints — query and export pipeline outputs.

Routes:
  GET    /results/run/{run_id}/workers         — Worker results
  GET    /results/run/{run_id}/claims          — Claims (paginated)
  GET    /results/run/{run_id}/contradictions  — Contradictions
  GET    /results/run/{run_id}/scores          — Scores
  GET    /results/run/{run_id}/summary         — Aggregated summary
  POST   /results/run/{run_id}/export          — Export all to S3
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from src.api.deps import CurrentUser, DbSession, Pagination
from src.schemas.result import (
    ClaimResponse,
    ContradictionResponse,
    ResultExportResponse,
    RunResultsSummary,
    ScoreResponse,
    WorkerResultResponse,
)
from src.services import result_service
from src.utils.pagination import build_paginated_response

router = APIRouter(prefix="/results", tags=["Results"])


@router.get(
    "/run/{run_id}/workers",
    summary="List worker results for a run",
)
async def list_worker_results(
    run_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[WorkerResultResponse]:
    """Fetch all worker results for a specific evaluation run."""
    workers = await result_service.get_worker_results_for_run(
        db, run_id=run_id, org_id=user.organization_id
    )
    return [WorkerResultResponse.model_validate(w) for w in workers]


@router.get(
    "/run/{run_id}/claims",
    summary="List claims for a run",
)
async def list_claims(
    run_id: UUID,
    user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    category: str | None = None,
) -> dict:
    """Fetch paginated claims extracted during evaluation."""
    claims, total = await result_service.get_claims_for_run(
        db,
        run_id=run_id,
        org_id=user.organization_id,
        category=category,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    items = [ClaimResponse.model_validate(c) for c in claims]
    return build_paginated_response(items, total, pagination)


@router.get(
    "/run/{run_id}/contradictions",
    summary="List contradictions for a run",
)
async def list_contradictions(
    run_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[ContradictionResponse]:
    """Fetch all contradictions detected during evaluation."""
    results = await result_service.get_contradictions_for_run(
        db, run_id=run_id, org_id=user.organization_id
    )
    return [ContradictionResponse.model_validate(c) for c in results]


@router.get(
    "/run/{run_id}/scores",
    summary="List scores for a run",
)
async def list_scores(
    run_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> list[ScoreResponse]:
    """Fetch all dimension scores for an evaluation run."""
    scores = await result_service.get_scores_for_run(
        db, run_id=run_id, org_id=user.organization_id
    )
    return [ScoreResponse.model_validate(s) for s in scores]


@router.get(
    "/run/{run_id}/summary",
    response_model=RunResultsSummary,
    summary="Get results summary for a run",
)
async def get_summary(
    run_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> RunResultsSummary:
    """
    Get aggregated pipeline output summary.

    Includes worker counts, claim/contradiction totals, scores,
    overall score, and progress percentage.
    """
    summary = await result_service.get_results_summary(
        db, run_id=run_id, org_id=user.organization_id
    )
    return RunResultsSummary(**summary)


@router.post(
    "/run/{run_id}/export",
    response_model=ResultExportResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Export results to S3",
)
async def export_results(
    run_id: UUID,
    user: CurrentUser,
    db: DbSession,
    fmt: str = "json",
) -> ResultExportResponse:
    """
    Export all pipeline results (workers, claims, contradictions, scores)
    for a run to S3. Returns a presigned download URL.
    """
    download_url = await result_service.export_results(
        db,
        run_id=run_id,
        org_id=user.organization_id,
        fmt=fmt,
    )
    return ResultExportResponse(
        export_id=str(run_id),
        status="completed",
        download_url=download_url,
    )
