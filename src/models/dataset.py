"""
Dataset model — collection of test samples for evaluation.

Datasets are stored in S3 with content-addressable storage:
- The SHA-256 checksum serves as a deduplication key
- Uploads use presigned URLs for zero-bandwidth-through-API transfers
- Schema versioning allows format evolution without breaking existing datasets

Status lifecycle:
  UPLOADING → VALIDATING → READY → ARCHIVED
                ↓
              FAILED (validation error)
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel


class DatasetStatus(str, enum.Enum):
    """Dataset lifecycle states."""

    UPLOADING = "uploading"  # presigned URL issued, waiting for upload
    VALIDATING = "validating"  # upload complete, validating format/schema
    READY = "ready"  # validated and available for evaluations
    FAILED = "failed"  # validation failed
    ARCHIVED = "archived"  # soft-archived, not available for new evaluations


class Dataset(BaseModel):
    """Collection of test samples stored in S3 for evaluation."""

    __tablename__ = "datasets"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Human-readable dataset name",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Optional description of dataset contents and purpose",
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Owning organization — datasets are not shared across orgs",
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="User who uploaded this dataset",
    )
    storage_path: Mapped[str] = mapped_column(
        String(1024),
        nullable=False,
        doc="S3 object key where the dataset file is stored",
    )
    sample_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Number of samples/rows in the dataset",
    )
    schema_version: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        default="1.0",
        doc="Dataset format version for backward compatibility",
    )
    checksum: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        index=True,
        doc="SHA-256 hash of the dataset file for integrity verification",
    )
    size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
        doc="File size in bytes",
    )
    status: Mapped[DatasetStatus] = mapped_column(
        SAEnum(DatasetStatus, name="dataset_status", create_constraint=True),
        nullable=False,
        default=DatasetStatus.UPLOADING,
        index=True,
        doc="Current lifecycle state",
    )
    # Flexible metadata: column names, data types, tags, etc.
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Extensible metadata (column schema, tags, source info)",
    )

    # ── Relationships ─────────────────────────────────────
    organization = relationship(
        "Organization", back_populates="datasets", lazy="joined"
    )
    created_by = relationship("User", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<Dataset(id={self.id}, name='{self.name}', "
            f"status='{self.status.value}')>"
        )
