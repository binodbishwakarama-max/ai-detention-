"""
Evaluation endpoints — pipeline config CRUD and run lifecycle.

Config Routes:
  POST   /evaluations/configs           — Create config
  GET    /evaluations/configs           — List configs
  GET    /evaluations/configs/{id}      — Get config
  PUT    /evaluations/configs/{id}      — Update config
  DELETE /evaluations/configs/{id}      — Delete config

Run Routes:
  GET    /evaluations/runs              — List runs
  GET    /evaluations/runs/{id}         — Get run detail
  POST   /evaluations/runs/{id}/cancel  — Cancel a run
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from src.api.deps import (
    CurrentUser,
    DbSession,
    Pagination,
    RequireAdmin,
    RequireMember,
    get_client_ip,
)
from src.schemas.common import MessageResponse
from src.schemas.evaluation import (
    EvaluationConfigCreate,
    EvaluationConfigResponse,
    EvaluationConfigUpdate,
    EvaluationRunResponse,
)
from src.services import evaluation_service
from src.utils.pagination import build_paginated_response

router = APIRouter(prefix="/evaluations", tags=["Evaluations"])


# ── Config CRUD ──────────────────────────────────────────


@router.post(
    "/configs",
    response_model=EvaluationConfigResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a pipeline configuration",
    dependencies=[RequireMember],
)
async def create_config(
    request: Request,
    body: EvaluationConfigCreate,
    user: CurrentUser,
    db: DbSession,
) -> EvaluationConfigResponse:
    """Create a new pipeline configuration template."""
    ip = get_client_ip(request)
    config = await evaluation_service.create_evaluation_config(
        db,
        org_id=user.organization_id,
        user_id=user.id,
        name=body.name,
        description=body.description,
        pipeline_config=body.pipeline_config,
        webhook_url=body.webhook_url,
        is_template=body.is_template,
        ip_address=ip,
    )
    return EvaluationConfigResponse.model_validate(config)


@router.get(
    "/configs",
    summary="List pipeline configurations",
)
async def list_configs(
    user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
) -> dict:
    """List pipeline configs for the authenticated user's organization."""
    configs, total = await evaluation_service.list_evaluation_configs(
        db,
        org_id=user.organization_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    items = [EvaluationConfigResponse.model_validate(c) for c in configs]
    return build_paginated_response(items, total, pagination)


@router.get(
    "/configs/{config_id}",
    response_model=EvaluationConfigResponse,
    summary="Get pipeline configuration",
)
async def get_config(
    config_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> EvaluationConfigResponse:
    """Fetch a specific pipeline config by ID."""
    config = await evaluation_service.get_evaluation_config(
        db, config_id=config_id, org_id=user.organization_id
    )
    return EvaluationConfigResponse.model_validate(config)


@router.put(
    "/configs/{config_id}",
    response_model=EvaluationConfigResponse,
    summary="Update pipeline configuration",
    dependencies=[RequireMember],
)
async def update_config(
    config_id: UUID,
    request: Request,
    body: EvaluationConfigUpdate,
    user: CurrentUser,
    db: DbSession,
) -> EvaluationConfigResponse:
    """Update a pipeline config. Increments version on each update."""
    ip = get_client_ip(request)
    updates = body.model_dump(exclude_unset=True)

    config = await evaluation_service.update_evaluation_config(
        db,
        config_id=config_id,
        org_id=user.organization_id,
        user_id=user.id,
        updates=updates,
        ip_address=ip,
    )
    return EvaluationConfigResponse.model_validate(config)


@router.delete(
    "/configs/{config_id}",
    response_model=MessageResponse,
    summary="Delete pipeline configuration",
    dependencies=[RequireAdmin],
)
async def delete_config(
    config_id: UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    """Soft-delete a pipeline configuration."""
    ip = get_client_ip(request)
    await evaluation_service.delete_evaluation_config(
        db,
        config_id=config_id,
        org_id=user.organization_id,
        user_id=user.id,
        ip_address=ip,
    )
    return MessageResponse(message="Configuration deleted successfully")


# ── Run Lifecycle ────────────────────────────────────────


@router.get(
    "/runs",
    summary="List evaluation runs",
)
async def list_runs(
    user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    submission_id: UUID | None = None,
    config_id: UUID | None = None,
    status_filter: str | None = None,
) -> dict:
    """List evaluation runs with optional filtering."""
    from src.models.evaluation import RunStatus

    parsed_status = None
    if status_filter:
        try:
            parsed_status = RunStatus(status_filter)
        except ValueError:
            pass

    runs, total = await evaluation_service.list_evaluation_runs(
        db,
        org_id=user.organization_id,
        submission_id=submission_id,
        config_id=config_id,
        status_filter=parsed_status,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    items = [EvaluationRunResponse.model_validate(r) for r in runs]
    return build_paginated_response(items, total, pagination)


@router.get(
    "/runs/{run_id}",
    response_model=EvaluationRunResponse,
    summary="Get evaluation run detail",
)
async def get_run(
    run_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> EvaluationRunResponse:
    """Fetch a specific evaluation run with full detail."""
    run = await evaluation_service.get_evaluation_run(
        db, run_id=run_id, org_id=user.organization_id
    )
    return EvaluationRunResponse.model_validate(run)


@router.post(
    "/runs/{run_id}/cancel",
    response_model=EvaluationRunResponse,
    summary="Cancel an evaluation run",
    dependencies=[RequireMember],
)
async def cancel_run(
    run_id: UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> EvaluationRunResponse:
    """Cancel a running or pending evaluation run."""
    ip = get_client_ip(request)
    run = await evaluation_service.cancel_evaluation_run(
        db,
        run_id=run_id,
        org_id=user.organization_id,
        user_id=user.id,
        ip_address=ip,
    )
    return EvaluationRunResponse.model_validate(run)
