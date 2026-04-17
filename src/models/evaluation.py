"""
Evaluation models — pipeline configuration and execution tracking.

EvaluationConfig: Reusable pipeline template defining how to evaluate a submission.
  Contains scoring weights, worker steps, LLM prompts, and feature flags.

EvaluationRun: A specific execution linking a Submission to evaluation criteria.
  Tracked by Celery workers with optimistic locking to prevent concurrent modification.

State machine:
  PENDING → RUNNING → COMPLETED
                    → FAILED
                    → CANCELLED (user-initiated)

Optimistic locking: The `version` column prevents lost-update anomalies
when multiple workers try to update the same run concurrently.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel, OptimisticLockMixin


class EvaluationConfig(BaseModel, OptimisticLockMixin):
    """
    Reusable pipeline configuration template.

    Defines *how* to evaluate a submission:
    - Which pipeline steps to run
    - Scoring weights per dimension
    - LLM prompts and evaluation rules
    - Feature flags for optional analysis
    """

    __tablename__ = "evaluation_configs"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    # ── Pipeline Definition ──────────────────────────────
    pipeline_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc=(
            "Pipeline definition: "
            "{steps: [...], weights: {...}, prompts: {...}, flags: {...}}"
        ),
    )
    webhook_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    is_template: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    organization = relationship("Organization", lazy="joined")
    created_by = relationship("User", lazy="joined")


class RunStatus(str, enum.Enum):
    """Evaluation run lifecycle states."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class EvaluationRun(BaseModel, OptimisticLockMixin):
    """
    A specific evaluation execution on a submission.

    Links a Submission (what) to an optional EvaluationConfig (how).
    Uses OptimisticLockMixin for concurrent-safe updates:
    workers must read the current version and include it in
    the WHERE clause when updating.
    """

    __tablename__ = "evaluation_runs"
    __table_args__ = (
        # Partial index: active runs per submission
        Index(
            "ix_evaluation_runs_submission_active",
            "submission_id",
            postgresql_where="deleted_at IS NULL",
        ),
        # Partial index: active runs by org + status (for dashboard queries)
        Index(
            "ix_evaluation_runs_org_status_active",
            "organization_id",
            "status",
            postgresql_where="deleted_at IS NULL",
        ),
        # Partial index: pending/running runs for worker pickup
        Index(
            "ix_evaluation_runs_pending_running",
            "status",
            "created_at",
            postgresql_where="(status = 'pending' OR status = 'running') AND deleted_at IS NULL",
        ),
    )

    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        doc="The submission being evaluated",
    )
    config_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_configs.id", ondelete="SET NULL"),
        nullable=True,
        doc="Optional pipeline config template used for this run",
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        doc="Denormalized org_id for RLS and fast filtering",
    )
    triggered_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        doc="User who initiated this run",
    )
    status: Mapped[RunStatus] = mapped_column(
        SAEnum(RunStatus, name="run_status", create_constraint=True),
        nullable=False,
        default=RunStatus.PENDING,
        doc="Current lifecycle state",
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When the first worker began processing",
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="When the run reached a terminal state",
    )
    # ── Worker Progress Tracking ──────────────────────────
    total_workers: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        doc="Number of workers assigned to this run",
    )
    completed_workers: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        doc="Number of workers that completed successfully",
    )
    failed_workers: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        doc="Number of workers that failed",
    )
    # ── Aggregate Results ──────────────────────────────────
    overall_score: Mapped[float | None] = mapped_column(
        Float, nullable=True,
        doc="Weighted aggregate score across all dimensions (0.0-1.0)",
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        doc="Error description if the run failed",
    )
    # ── Celery Tracking ────────────────────────────────────
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
        doc="Celery task ID for status tracking and cancellation",
    )
    # ── Snapshots ──────────────────────────────────────────
    config_snapshot: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default="{}",
        doc="Frozen copy of pipeline config used for this run",
    )
    run_metadata: Mapped[dict] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict, server_default="{}",
        doc="Custom metadata: {triggered_from, git_sha, tags, ...}",
    )

    # ── Relationships ─────────────────────────────────────
    submission = relationship("Submission", back_populates="evaluation_runs", lazy="joined")
    config = relationship("EvaluationConfig", lazy="joined")
    organization = relationship("Organization", lazy="joined")
    triggered_by = relationship("User", lazy="joined")
    worker_results = relationship("WorkerResult", back_populates="evaluation_run", lazy="noload")
    claims = relationship("Claim", back_populates="evaluation_run", lazy="noload")
    contradictions = relationship("Contradiction", back_populates="evaluation_run", lazy="noload")
    scores = relationship("Score", back_populates="evaluation_run", lazy="noload")

    @property
    def progress_pct(self) -> float:
        """Completion percentage, safe against division by zero."""
        if self.total_workers == 0:
            return 0.0
        return round((self.completed_workers / self.total_workers) * 100, 2)

    @property
    def is_terminal(self) -> bool:
        """Whether the run has reached a final state."""
        return self.status in (RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.CANCELLED)

    def __repr__(self) -> str:
        return (
            f"<EvaluationRun(id={self.id}, status='{self.status.value}', "
            f"v{self.version}, progress={self.progress_pct}%)>"
        )
