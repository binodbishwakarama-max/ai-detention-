"""Metric endpoints."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Request, status

from src.api.deps import (
    CurrentUser,
    DbSession,
    Pagination,
    RequireMember,
    get_client_ip,
)
from src.schemas.metric import MetricCreate, MetricResponse
from src.services import metric_service
from src.utils.pagination import build_paginated_response

router = APIRouter(prefix="/metrics", tags=["Metrics"])


@router.get(
    "",
    summary="List available metrics",
)
async def list_metrics(
    user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
) -> dict:
    """List all metrics available to the current organization (built-in + custom)."""
    metrics, total = await metric_service.list_metrics(
        db,
        org_id=user.organization_id,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    items = [MetricResponse.model_validate(m) for m in metrics]
    return build_paginated_response(items, total, pagination)


@router.get(
    "/{metric_id}",
    response_model=MetricResponse,
    summary="Get a metric",
)
async def get_metric(
    metric_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> MetricResponse:
    """Fetch a specific metric by ID."""
    metric = await metric_service.get_metric(
        db, metric_id=metric_id, org_id=user.organization_id
    )
    return MetricResponse.model_validate(metric)


@router.post(
    "",
    response_model=MetricResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a custom metric",
    dependencies=[RequireMember],
)
async def create_metric(
    request: Request,
    body: MetricCreate,
    user: CurrentUser,
    db: DbSession,
) -> MetricResponse:
    """Create a custom metric scoped to the current organization."""
    ip = get_client_ip(request)
    metric = await metric_service.create_custom_metric(
        db,
        org_id=user.organization_id,
        user_id=user.id,
        name=body.name,
        display_name=body.display_name,
        description=body.description,
        metric_type=body.metric_type,
        computation_config=body.computation_config,
        higher_is_better=body.higher_is_better,
        min_value=body.min_value,
        max_value=body.max_value,
        ip_address=ip,
    )
    return MetricResponse.model_validate(metric)
