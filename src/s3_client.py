"""
S3-compatible object storage client.

Supports both AWS S3 and MinIO for local development.
Uses boto3 synchronously because aiobotocore has compatibility issues
with newer boto3 versions. For async contexts, wrap calls in
asyncio.to_thread() at the service layer.

Key design decisions:
- Presigned URLs for uploads: clients upload directly to S3, bypassing our API
- Content-addressable storage: datasets stored by SHA-256 hash for deduplication
- Server-side encryption: SSE-S3 enabled by default
"""

from __future__ import annotations

import hashlib
import io
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import ClientError

from src.config import get_settings

# ── Client ──────────────────────────────────────────────────
_client: Any = None


def get_s3_client() -> Any:
    """
    Return the global S3 client.

    boto3 clients are thread-safe and can be shared across threads.
    Connection pooling is handled internally by urllib3.
    """
    global _client
    if _client is None:
        settings = get_settings()
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
            config=BotoConfig(
                max_pool_connections=25,
                retries={"max_attempts": 3, "mode": "adaptive"},
                connect_timeout=5,
                read_timeout=30,
            ),
        )
    return _client


def ensure_bucket_exists() -> None:
    """Create the storage bucket if it doesn't exist. Called at startup."""
    settings = get_settings()
    client = get_s3_client()
    try:
        client.head_bucket(Bucket=settings.s3_bucket_name)
    except ClientError:
        client.create_bucket(Bucket=settings.s3_bucket_name)


def generate_presigned_upload_url(
    key: str,
    content_type: str = "application/octet-stream",
    expiry: int | None = None,
) -> str:
    """
    Generate a presigned URL for direct client-to-S3 upload.

    This eliminates the need to proxy large dataset files through our API,
    reducing server bandwidth and latency. The client uploads directly to S3
    with a time-limited, scoped URL.
    """
    settings = get_settings()
    client = get_s3_client()
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket_name,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expiry or settings.s3_presigned_url_expiry,
    )


def generate_presigned_download_url(
    key: str,
    expiry: int | None = None,
) -> str:
    """Generate a presigned URL for downloading an object from S3."""
    settings = get_settings()
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.s3_bucket_name,
            "Key": key,
        },
        ExpiresIn=expiry or settings.s3_presigned_url_expiry,
    )


def upload_bytes(
    key: str, data: bytes, content_type: str = "application/octet-stream"
) -> str:
    """
    Upload raw bytes to S3 and return the SHA-256 checksum.

    Used for server-side uploads of small files (e.g., evaluation reports).
    For large datasets, use presigned URLs instead.
    """
    settings = get_settings()
    client = get_s3_client()
    checksum = hashlib.sha256(data).hexdigest()
    client.put_object(
        Bucket=settings.s3_bucket_name,
        Key=key,
        Body=io.BytesIO(data),
        ContentType=content_type,
        ServerSideEncryption="AES256",
        Metadata={"sha256": checksum},
    )
    return checksum


def download_bytes(key: str) -> bytes:
    """Download an object from S3 and return its contents as bytes."""
    settings = get_settings()
    client = get_s3_client()
    response = client.get_object(Bucket=settings.s3_bucket_name, Key=key)
    return response["Body"].read()


def delete_object(key: str) -> None:
    """Delete an object from S3."""
    settings = get_settings()
    client = get_s3_client()
    client.delete_object(Bucket=settings.s3_bucket_name, Key=key)


def object_exists(key: str) -> bool:
    """Check if an object exists in S3."""
    settings = get_settings()
    client = get_s3_client()
    try:
        client.head_object(Bucket=settings.s3_bucket_name, Key=key)
        return True
    except ClientError:
        return False
