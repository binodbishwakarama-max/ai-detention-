"""
Submission model — the startup being evaluated.

A submission represents a startup's application that will go through
one or more evaluation runs. Each submission captures the raw data
(pitch deck URL, website, team info) and can be re-evaluated as
the evaluation criteria evolve.

Status lifecycle:
  DRAFT → SUBMITTED → UNDER_REVIEW → EVALUATED → ARCHIVED
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel


class SubmissionStatus(str, enum.Enum):
    """Submission lifecycle states."""
    DRAFT = "draft"
    SUBMITTED = "submitted"
    UNDER_REVIEW = "under_review"
    EVALUATED = "evaluated"
    ARCHIVED = "archived"


class Submission(BaseModel):
    """A startup submission to be evaluated."""

    __tablename__ = "submissions"
    __table_args__ = (
        # Partial index: active submissions per org, filtered by status
        Index(
            "ix_submissions_org_status_active",
            "organization_id",
            "status",
            postgresql_where="deleted_at IS NULL",
        ),
        # Partial index: fast lookup by org for active submissions
        Index(
            "ix_submissions_org_active",
            "organization_id",
            postgresql_where="deleted_at IS NULL",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        doc="Owning organization — submissions scoped to org",
    )
    submitted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="User who submitted this entry",
    )
    startup_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Name of the startup being evaluated",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Short description / elevator pitch",
    )
    website_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        doc="Startup website URL",
    )
    pitch_deck_url: Mapped[str | None] = mapped_column(
        String(2048),
        nullable=True,
        doc="URL to the pitch deck (S3 presigned URL or external link)",
    )
    status: Mapped[SubmissionStatus] = mapped_column(
        SAEnum(SubmissionStatus, name="submission_status", create_constraint=True, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=SubmissionStatus.DRAFT,
        doc="Current lifecycle state",
    )
    # Flexible metadata: founding date, team size, funding stage, sector, etc.
    metadata_: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Extensible metadata (sector, funding_stage, team_size, ...)",
    )
    # Raw content extracted from pitch deck / website for analysis
    raw_content: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Extracted text content from pitch deck / website",
    )

    # ── Relationships ─────────────────────────────────────
    organization = relationship("Organization", back_populates="submissions", lazy="joined")
    submitted_by = relationship("User", lazy="joined")
    evaluation_runs = relationship("EvaluationRun", back_populates="submission", lazy="noload")

    def __repr__(self) -> str:
        return (
            f"<Submission(id={self.id}, startup='{self.startup_name}', "
            f"status='{self.status.value}')>"
        )
