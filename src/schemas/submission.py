"""Submission schemas — create, update, and response for startup submissions."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.models.submission import SubmissionStatus
from src.schemas.common import BaseSchema, TimestampSchema


# ── Request Schemas ──────────────────────────────────────


class SubmissionCreate(BaseModel):
    """Schema for creating a new startup submission."""

    startup_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    website_url: str | None = Field(
        default=None,
        max_length=2048,
        description="Startup website URL",
    )
    pitch_deck_url: str | None = Field(
        default=None,
        max_length=2048,
        description="URL to the pitch deck (S3 presigned or external)",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Extensible metadata: {sector, funding_stage, team_size, ...}",
    )


class SubmissionUpdate(BaseModel):
    """Schema for updating a submission."""

    startup_name: str | None = None
    description: str | None = None
    website_url: str | None = None
    pitch_deck_url: str | None = None
    status: SubmissionStatus | None = None
    metadata: dict | None = None


class SubmissionEvaluate(BaseModel):
    """Schema for triggering an evaluation on a submission."""

    config_id: UUID | None = Field(
        default=None,
        description="Optional pipeline config template to use. If omitted, uses defaults.",
    )
    metadata: dict = Field(
        default_factory=dict,
        description="Run metadata: {triggered_from, git_sha, tags, ...}",
    )


# ── Response Schemas ─────────────────────────────────────


class SubmissionResponse(TimestampSchema):
    """Submission response with full detail."""

    id: UUID
    organization_id: UUID
    submitted_by_id: UUID | None
    startup_name: str
    description: str | None
    website_url: str | None
    pitch_deck_url: str | None
    status: SubmissionStatus
    metadata: dict = Field(alias="metadata_")
