"""
Dataset endpoints — upload, confirm, query, and delete datasets.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request, status

from src.api.deps import (
    CurrentUser,
    DbSession,
    Pagination,
    RequireMember,
    get_client_ip,
)
from src.config import get_settings
from src.models.dataset import DatasetStatus
from src.schemas.common import MessageResponse
from src.schemas.dataset import (
    DatasetConfirmUpload,
    DatasetCreate,
    DatasetCreateResponse,
    DatasetResponse,
)
from src.services import dataset_service
from src.utils.pagination import build_paginated_response

router = APIRouter(prefix="/datasets", tags=["Datasets"])


@router.post(
    "",
    response_model=DatasetCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate a dataset upload",
    dependencies=[RequireMember],
)
async def create_dataset(
    request: Request,
    body: DatasetCreate,
    user: CurrentUser,
    db: DbSession,
) -> DatasetCreateResponse:
    """
    Initiate a dataset upload.

    Returns a presigned S3 URL for direct upload. The client should
    upload the file to this URL, then call POST /datasets/{id}/confirm
    with the SHA-256 checksum.
    """
    ip = get_client_ip(request)
    settings = get_settings()
    dataset, upload_url = await dataset_service.initiate_dataset_upload(
        db,
        org_id=user.organization_id,
        user_id=user.id,
        name=body.name,
        description=body.description,
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        metadata=body.metadata,
        ip_address=ip,
    )
    response = DatasetCreateResponse.model_validate(dataset)
    response.upload_url = upload_url
    response.upload_expires_in = settings.s3_presigned_url_expiry
    return response


@router.post(
    "/{dataset_id}/confirm",
    response_model=DatasetResponse,
    summary="Confirm dataset upload",
    dependencies=[RequireMember],
)
async def confirm_upload(
    request: Request,
    dataset_id: UUID,
    body: DatasetConfirmUpload,
    user: CurrentUser,
    db: DbSession,
) -> DatasetResponse:
    """
    Confirm a dataset upload is complete.

    Validates the SHA-256 checksum against the uploaded file
    and transitions the dataset to READY state.
    """
    ip = get_client_ip(request)
    dataset = await dataset_service.confirm_dataset_upload(
        db,
        dataset_id=dataset_id,
        org_id=user.organization_id,
        checksum=body.checksum,
        sample_count=body.sample_count,
        ip_address=ip,
    )
    return DatasetResponse.model_validate(dataset)


@router.get(
    "",
    summary="List datasets",
)
async def list_datasets(
    user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    status_filter: DatasetStatus | None = Query(
        default=None,
        alias="status",
        description="Filter by dataset status",
    ),
) -> dict:
    """List datasets for the current organization."""
    datasets, total = await dataset_service.list_datasets(
        db,
        org_id=user.organization_id,
        status_filter=status_filter,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    items = [DatasetResponse.model_validate(d) for d in datasets]
    return build_paginated_response(items, total, pagination)


@router.get(
    "/{dataset_id}",
    response_model=DatasetResponse,
    summary="Get a dataset",
)
async def get_dataset(
    dataset_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> DatasetResponse:
    """Fetch a specific dataset by ID."""
    dataset = await dataset_service.get_dataset(
        db, dataset_id=dataset_id, org_id=user.organization_id
    )
    return DatasetResponse.model_validate(dataset)


@router.delete(
    "/{dataset_id}",
    response_model=MessageResponse,
    summary="Delete a dataset",
    dependencies=[RequireMember],
)
async def delete_dataset(
    request: Request,
    dataset_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    """Soft-delete a dataset. S3 files are cleaned up by background worker."""
    ip = get_client_ip(request)
    await dataset_service.delete_dataset(
        db,
        dataset_id=dataset_id,
        org_id=user.organization_id,
        user_id=user.id,
        ip_address=ip,
    )
    return MessageResponse(message="Dataset deleted successfully")
