"""Dataset schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from src.models.dataset import DatasetStatus
from src.schemas.common import TimestampSchema


class DatasetCreate(BaseModel):
    """Schema for initiating a dataset upload."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    content_type: str = Field(
        default="application/json",
        description="MIME type of the dataset file",
    )
    size_bytes: int = Field(gt=0, description="File size in bytes")
    metadata: dict = Field(default_factory=dict)


class DatasetCreateResponse(TimestampSchema):
    """Response after initiating dataset upload — includes presigned URL."""

    id: UUID
    name: str
    status: DatasetStatus
    upload_url: str = Field(
        description="S3 presigned URL for direct upload"
    )
    upload_expires_in: int = Field(
        description="Upload URL TTL in seconds"
    )


class DatasetConfirmUpload(BaseModel):
    """Schema for confirming a dataset upload is complete."""

    checksum: str = Field(
        min_length=64,
        max_length=64,
        description=(
            "SHA-256 hash of the uploaded file for integrity verification"
        ),
    )
    sample_count: int = Field(
        ge=1, description="Number of samples in the dataset"
    )


class DatasetResponse(TimestampSchema):
    """Dataset details response."""

    id: UUID
    name: str
    description: str | None
    organization_id: UUID
    created_by_id: UUID | None
    sample_count: int
    schema_version: str
    checksum: str
    size_bytes: int
    status: DatasetStatus
    metadata: dict


class DatasetUpdate(BaseModel):
    """Schema for updating dataset metadata."""

    name: str | None = None
    description: str | None = None
    metadata: dict | None = None
