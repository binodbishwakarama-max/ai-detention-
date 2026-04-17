"""
Base model with production-grade patterns.

Design decisions:
- UUID7 primary keys: time-ordered for B-tree index locality, globally unique.
- Soft deletes everywhere: deleted_at IS NOT NULL means logically deleted.
  Partial indexes filter out deleted rows so they don't slow queries.
- Optimistic locking mixin: prevents lost-update anomalies on concurrent writes.
- created_at/updated_at: automatic timestamps, server-side defaults.
- All defaults are database-level to ensure consistency even when bypassing ORM.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, event, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from uuid6 import uuid7


class Base(DeclarativeBase):
    """
    Abstract base for all SQLAlchemy models.
    Provides the registry and metadata for Alembic migrations.
    """
    pass


class TimestampMixin:
    """Mixin providing created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        doc="Record creation timestamp, set by the database",
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("NOW()"),
        onupdate=lambda: datetime.now(timezone.utc),
        doc="Last modification timestamp, updated on every write",
    )


class SoftDeleteMixin:
    """
    Mixin providing soft-delete capability.

    Records are never physically deleted through the API. deleted_at is set
    to the current timestamp on deletion. A background worker handles
    physical deletion after the GDPR-mandated retention period (30 days).

    All query repositories automatically filter is_deleted=False unless
    explicitly told to include deleted records.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
        index=False,  # partial index on non-null is better; see migration
        doc="Timestamp of soft deletion, NULL means active",
    )

    @property
    def is_deleted(self) -> bool:
        """Whether the record has been soft-deleted."""
        return self.deleted_at is not None

    def soft_delete(self) -> None:
        """Mark this record as soft-deleted."""
        self.deleted_at = datetime.now(timezone.utc)

    def restore(self) -> None:
        """Restore a soft-deleted record."""
        self.deleted_at = None


class OptimisticLockMixin:
    """
    Mixin providing optimistic locking via a version column.

    On every UPDATE, the version is incremented. If two concurrent
    transactions try to update the same row, one will fail because
    the WHERE version=X clause won't match.

    Usage in repository:
        stmt = update(Model).where(
            Model.id == id,
            Model.version == expected_version
        ).values(version=expected_version + 1, ...)

        result = await db.execute(stmt)
        if result.rowcount == 0:
            raise ConflictError("Concurrent modification detected")
    """

    version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default=text("1"),
        doc="Optimistic lock version — incremented on every update",
    )


def generate_uuid7() -> uuid.UUID:
    """
    Generate a UUID v7 (time-ordered).

    UUID7 provides:
    - 48-bit Unix timestamp (millisecond precision) in MSBs
    - Natural time ordering for efficient B-tree indexing
    - Global uniqueness without coordination
    """
    return uuid7()


class BaseModel(Base, TimestampMixin, SoftDeleteMixin):
    """
    Concrete base model that all domain entities extend.

    Provides:
    - UUID7 primary key
    - created_at / updated_at timestamps
    - Soft delete with deleted_at
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=generate_uuid7,
        doc="UUID7 primary key — time-ordered for index locality",
    )
