"""
Dataset service — CRUD operations for datasets.

Handles the dataset lifecycle:
1. Client requests upload → service creates record + returns presigned URL
2. Client uploads directly to S3
3. Client confirms upload → service validates checksum + marks READY
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.error_handler import ConflictError, NotFoundError
from src.models.audit_log import AuditAction
from src.models.dataset import Dataset, DatasetStatus
from src.services.audit_service import create_audit_log
from src.services.storage_service import (
    delete_dataset_files,
    get_dataset_upload_url,
    verify_dataset_integrity,
)

logger = structlog.get_logger(__name__)


async def initiate_dataset_upload(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    name: str,
    description: str | None = None,
    content_type: str = "application/json",
    size_bytes: int = 0,
    metadata: dict | None = None,
    ip_address: str | None = None,
) -> tuple[Dataset, str]:
    """
    Create a dataset record and generate a presigned upload URL.

    Returns:
        Tuple of (dataset, presigned_upload_url)
    """
    from src.models.base import generate_uuid7

    dataset_id = generate_uuid7()

    # Generate presigned URL and storage path
    upload_url, storage_path = get_dataset_upload_url(
        org_id, dataset_id
    )

    dataset = Dataset(
        id=dataset_id,
        name=name,
        description=description,
        organization_id=org_id,
        created_by_id=user_id,
        storage_path=storage_path,
        size_bytes=size_bytes,
        checksum="pending",  # will be set on confirmation
        status=DatasetStatus.UPLOADING,
        metadata_=metadata or {},
    )
    db.add(dataset)
    await db.flush()

    await create_audit_log(
        db,
        action=AuditAction.CREATE,
        resource_type="dataset",
        resource_id=str(dataset.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )

    logger.info(
        "dataset.upload_initiated",
        dataset_id=str(dataset.id),
        org_id=str(org_id),
    )
    return dataset, upload_url


async def confirm_dataset_upload(
    db: AsyncSession,
    *,
    dataset_id: UUID,
    org_id: UUID,
    checksum: str,
    sample_count: int,
    ip_address: str | None = None,
) -> Dataset:
    """
    Confirm a dataset upload is complete.

    Validates the checksum against the uploaded file in S3 and
    transitions the dataset to READY state.
    """
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.organization_id == org_id,
            Dataset.is_deleted == False,  # noqa: E712
        )
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise NotFoundError("Dataset", str(dataset_id))

    if dataset.status != DatasetStatus.UPLOADING:
        raise ConflictError(
            f"Dataset is in '{dataset.status.value}' state, "
            "expected 'uploading'"
        )

    # Transition to VALIDATING
    dataset.status = DatasetStatus.VALIDATING
    await db.flush()

    # Verify integrity
    if not verify_dataset_integrity(dataset.storage_path, checksum):
        dataset.status = DatasetStatus.FAILED
        await db.flush()
        raise ConflictError(
            "Checksum verification failed — file may be corrupted"
        )

    # Mark as ready
    dataset.checksum = checksum
    dataset.sample_count = sample_count
    dataset.status = DatasetStatus.READY
    await db.flush()

    await create_audit_log(
        db,
        action=AuditAction.DATASET_UPLOADED,
        resource_type="dataset",
        resource_id=str(dataset.id),
        organization_id=org_id,
        ip_address=ip_address,
    )

    logger.info(
        "dataset.upload_confirmed",
        dataset_id=str(dataset.id),
        sample_count=sample_count,
    )
    return dataset


async def get_dataset(
    db: AsyncSession,
    *,
    dataset_id: UUID,
    org_id: UUID,
) -> Dataset:
    """Fetch a dataset by ID, scoped to an organization."""
    result = await db.execute(
        select(Dataset).where(
            Dataset.id == dataset_id,
            Dataset.organization_id == org_id,
            Dataset.is_deleted == False,  # noqa: E712
        )
    )
    dataset = result.scalar_one_or_none()
    if not dataset:
        raise NotFoundError("Dataset", str(dataset_id))
    return dataset


async def list_datasets(
    db: AsyncSession,
    *,
    org_id: UUID,
    status_filter: DatasetStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Dataset], int]:
    """List datasets for an organization with pagination."""
    base_where = [
        Dataset.organization_id == org_id,
        Dataset.is_deleted == False,  # noqa: E712
    ]
    if status_filter:
        base_where.append(Dataset.status == status_filter)

    count_stmt = (
        select(func.count())
        .select_from(Dataset)
        .where(*base_where)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Dataset)
        .where(*base_where)
        .order_by(Dataset.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    datasets = list(result.scalars().all())

    return datasets, total


async def delete_dataset(
    db: AsyncSession,
    *,
    dataset_id: UUID,
    org_id: UUID,
    user_id: UUID,
    ip_address: str | None = None,
) -> None:
    """Soft-delete a dataset and schedule S3 file cleanup."""
    dataset = await get_dataset(
        db, dataset_id=dataset_id, org_id=org_id
    )
    dataset.soft_delete()
    await db.flush()

    # Schedule S3 cleanup (handled by cleanup_worker)
    # Files are not deleted immediately to support soft-delete recovery
    await create_audit_log(
        db,
        action=AuditAction.DATASET_DELETED,
        resource_type="dataset",
        resource_id=str(dataset.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )

    logger.info(
        "dataset.deleted",
        dataset_id=str(dataset.id),
    )
