"""
Result schemas — aggregated pipeline outputs.

Results are derived from WorkerResult, Claim, Contradiction, and Score models.
The legacy EvaluationResult model has been removed.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from src.schemas.common import BaseSchema, TimestampSchema


class WorkerResultResponse(TimestampSchema):
    """Individual worker result within an evaluation run."""

    id: UUID
    evaluation_run_id: UUID
    worker_type: str
    status: str
    processing_time_ms: int
    output_data: dict
    error_message: str | None


class ClaimResponse(TimestampSchema):
    """Claim extracted from a submission."""

    id: UUID
    evaluation_run_id: UUID
    claim_text: str
    category: str
    source_reference: str | None
    confidence_score: float
    verification_status: str
    evidence: dict


class ContradictionResponse(TimestampSchema):
    """Contradiction detected between two claims."""

    id: UUID
    evaluation_run_id: UUID
    claim_a_id: UUID
    claim_b_id: UUID
    contradiction_type: str
    severity: float
    explanation: str


class ScoreResponse(TimestampSchema):
    """Score for a single dimension within an evaluation run."""

    id: UUID
    evaluation_run_id: UUID
    dimension: str
    value: float
    weight: float
    rationale: str | None
    breakdown: dict


class RunResultsSummary(BaseSchema):
    """Aggregated summary of all pipeline outputs for a run."""

    run_id: UUID
    status: str
    overall_score: float | None
    total_workers: int
    completed_workers: int
    failed_workers: int
    total_claims: int
    total_contradictions: int
    scores: list[ScoreResponse]
    progress_pct: float


class ResultExportRequest(BaseModel):
    """Schema for requesting a result export to S3."""

    run_id: UUID
    format: str = Field(
        default="json",
        pattern="^(json|csv)$",
        description="Export format: json or csv",
    )


class ResultExportResponse(BaseSchema):
    """Response after initiating a result export."""

    export_id: str
    status: str = "processing"
    download_url: str | None = None
