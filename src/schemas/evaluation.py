"""Evaluation configuration and run schemas — aligned with Submission pipeline."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.models.evaluation import RunStatus
from src.schemas.common import BaseSchema, TimestampSchema


# ── Evaluation Config (Pipeline Template) ─────────────────


class EvaluationConfigCreate(BaseModel):
    """Schema for creating a pipeline configuration template."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    pipeline_config: dict = Field(
        default_factory=dict,
        description=(
            "Pipeline definition: "
            "{steps: [...], weights: {...}, prompts: {...}, flags: {...}}"
        ),
    )
    webhook_url: str | None = Field(
        default=None,
        max_length=2048,
        description="Webhook URL for completion callback",
    )
    is_template: bool = False


class EvaluationConfigUpdate(BaseModel):
    """Schema for updating a pipeline configuration template."""

    name: str | None = None
    description: str | None = None
    pipeline_config: dict | None = None
    webhook_url: str | None = None
    is_template: bool | None = None


class EvaluationConfigResponse(TimestampSchema):
    """Pipeline configuration response."""

    id: UUID
    name: str
    description: str | None
    organization_id: UUID
    created_by_id: UUID | None
    pipeline_config: dict
    webhook_url: str | None
    is_template: bool
    version: int


# ── Evaluation Run ───────────────────────────────────────


class EvaluationRunResponse(TimestampSchema):
    """Evaluation run response with full detail."""

    id: UUID
    submission_id: UUID
    config_id: UUID | None
    organization_id: UUID
    triggered_by_id: UUID | None
    status: RunStatus
    started_at: datetime | None
    completed_at: datetime | None
    total_workers: int
    completed_workers: int
    failed_workers: int
    overall_score: float | None
    error_message: str | None
    celery_task_id: str | None
    config_snapshot: dict
    metadata: dict = Field(alias="run_metadata")
    progress_pct: float
