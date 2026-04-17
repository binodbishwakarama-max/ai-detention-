"""
WorkerResult model — one row per worker per evaluation run.

Each evaluation run is split across multiple workers for parallelism.
Each worker processes a subset of the evaluation and reports its findings:
- Extracted claims
- Detected contradictions
- Per-dimension scores

The worker_type field identifies what kind of analysis was performed
(e.g., 'claim_extraction', 'fact_checking', 'scoring').
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel


class WorkerStatus(str, enum.Enum):
    """Worker execution states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkerResult(BaseModel):
    """Result from a single worker within an evaluation run."""

    __tablename__ = "worker_results"
    __table_args__ = (
        # Composite index for looking up all workers for a run
        Index(
            "ix_worker_results_run_active",
            "evaluation_run_id",
            postgresql_where="deleted_at IS NULL",
        ),
        # Partial index: find in-progress workers
        Index(
            "ix_worker_results_status_active",
            "evaluation_run_id",
            "status",
            postgresql_where="deleted_at IS NULL",
        ),
    )

    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        doc="Parent evaluation run",
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        doc="Denormalized org_id for RLS",
    )
    worker_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Type of analysis: 'claim_extraction', 'fact_checking', 'scoring'",
    )
    worker_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Celery worker hostname that executed this task",
    )
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        doc="Celery task ID for this specific worker",
    )
    status: Mapped[WorkerStatus] = mapped_column(
        SAEnum(WorkerStatus, name="worker_status", create_constraint=True),
        nullable=False,
        default=WorkerStatus.PENDING,
        doc="Worker execution state",
    )
    processing_time_ms: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        doc="Processing time in milliseconds",
    )
    # Raw output from this worker (claim list, contradiction list, etc.)
    output_data: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        doc="Worker output: varies by worker_type",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        doc="Error message if the worker failed",
    )

    # ── Relationships ─────────────────────────────────────
    evaluation_run = relationship("EvaluationRun", back_populates="worker_results", lazy="joined")
    organization = relationship("Organization", lazy="noload")

    def __repr__(self) -> str:
        return (
            f"<WorkerResult(id={self.id}, type='{self.worker_type}', "
            f"status='{self.status.value}')>"
        )
