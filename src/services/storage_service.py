"""
Storage service — abstraction over S3 operations.

Provides high-level operations for dataset and result storage:
- Presigned URL generation for client-side uploads
- Dataset file management
- Evaluation result export to S3
- Content integrity verification via SHA-256
"""

from __future__ import annotations

import hashlib
from uuid import UUID

import structlog

from src.s3_client import (
    delete_object,
    download_bytes,
    generate_presigned_download_url,
    generate_presigned_upload_url,
    object_exists,
    upload_bytes,
)

logger = structlog.get_logger(__name__)


def generate_dataset_key(org_id: UUID, dataset_id: UUID) -> str:
    """
    Generate a deterministic S3 key for a dataset.

    Format: datasets/{org_id}/{dataset_id}/data.json
    Using org_id as a prefix enables efficient per-org listing and
    provides a natural data isolation boundary in S3.
    """
    return f"datasets/{org_id}/{dataset_id}/data.json"


def generate_export_key(
    org_id: UUID, run_id: UUID, fmt: str
) -> str:
    """Generate S3 key for evaluation result exports."""
    return f"exports/{org_id}/{run_id}/results.{fmt}"


def get_dataset_upload_url(
    org_id: UUID, dataset_id: UUID
) -> tuple[str, str]:
    """
    Generate a presigned upload URL for a dataset.

    Returns:
        Tuple of (presigned_url, storage_path)
    """
    key = generate_dataset_key(org_id, dataset_id)
    url = generate_presigned_upload_url(
        key, content_type="application/json"
    )
    return url, key


def get_dataset_download_url(storage_path: str) -> str:
    """Generate a presigned download URL for a dataset."""
    return generate_presigned_download_url(storage_path)


def get_export_download_url(
    org_id: UUID, run_id: UUID, fmt: str
) -> str:
    """Generate a presigned download URL for an export file."""
    key = generate_export_key(org_id, run_id, fmt)
    return generate_presigned_download_url(key)


def upload_export_data(
    org_id: UUID, run_id: UUID, data: bytes, fmt: str
) -> str:
    """Upload export data to S3 and return the checksum."""
    key = generate_export_key(org_id, run_id, fmt)
    content_type_map = {
        "json": "application/json",
        "csv": "text/csv",
        "parquet": "application/octet-stream",
    }
    checksum = upload_bytes(
        key,
        data,
        content_type_map.get(fmt, "application/octet-stream"),
    )
    logger.info(
        "storage.export_uploaded",
        key=key,
        size=len(data),
        checksum=checksum,
    )
    return checksum


def verify_dataset_integrity(
    storage_path: str, expected_checksum: str
) -> bool:
    """
    Verify dataset integrity by comparing SHA-256 checksums.

    Downloads the file and computes the hash. For very large files,
    consider streaming the hash computation.
    """
    try:
        data = download_bytes(storage_path)
        actual = hashlib.sha256(data).hexdigest()
        return actual == expected_checksum
    except Exception:
        logger.exception(
            "storage.integrity_check_failed", path=storage_path
        )
        return False


def delete_dataset_files(org_id: UUID, dataset_id: UUID) -> None:
    """Delete all S3 objects associated with a dataset."""
    key = generate_dataset_key(org_id, dataset_id)
    if object_exists(key):
        delete_object(key)
        logger.info("storage.dataset_deleted", key=key)
