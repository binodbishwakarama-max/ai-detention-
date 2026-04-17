"""
Score model — one row per scoring dimension per evaluation run.

Scores are IMMUTABLE after initial write. Once a score is recorded
for a dimension in a run, it cannot be updated or deleted — this
provides a trustworthy audit trail for evaluation integrity.

Scoring dimensions include:
- market_opportunity (TAM, SAM, SOM analysis)
- team_strength (experience, domain expertise)
- product_viability (technology, differentiation)
- financial_health (revenue, burn rate, projections)
- traction (users, growth rate, partnerships)
- overall (weighted aggregate)

Immutability is enforced at the application level (repository)
and at the database level (trigger in migration).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy import CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel


class Score(BaseModel):
    """
    Immutable score for a single dimension within an evaluation run.

    Once created, Score rows are never updated or deleted.
    To re-score, create a new evaluation run.
    """

    __tablename__ = "scores"
    __table_args__ = (
        # Unique constraint: one score per dimension per run
        Index(
            "uq_scores_run_dimension_active",
            "evaluation_run_id",
            "dimension",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        # Index: all scores for a run
        Index(
            "ix_scores_run_active",
            "evaluation_run_id",
            postgresql_where="deleted_at IS NULL",
        ),
        # Index: org-level score analytics
        Index(
            "ix_scores_org_dimension_active",
            "organization_id",
            "dimension",
            postgresql_where="deleted_at IS NULL",
        ),
        # Check constraint: score must be between 0 and 1
        CheckConstraint(
            "value >= 0.0 AND value <= 1.0",
            name="ck_scores_value_range",
        ),
        # Check constraint: weight must be between 0 and 1
        CheckConstraint(
            "weight >= 0.0 AND weight <= 1.0",
            name="ck_scores_weight_range",
        ),
    )

    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        doc="The evaluation run this score belongs to",
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        doc="Denormalized org_id for RLS",
    )
    dimension: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Scoring dimension: 'market_opportunity', 'team_strength', etc.",
    )
    value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Score value (0.0 to 1.0)",
    )
    weight: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        doc="Weight of this dimension in the overall score (0.0 to 1.0)",
    )
    rationale: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Human/AI-readable justification for this score",
    )
    # Detailed breakdown
    breakdown: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Detailed score breakdown: {sub_criteria: score, evidence: [...]}",
    )

    # ── Relationships ─────────────────────────────────────
    evaluation_run = relationship("EvaluationRun", back_populates="scores", lazy="joined")
    organization = relationship("Organization", lazy="noload")

    def __repr__(self) -> str:
        return (
            f"<Score(id={self.id}, dimension='{self.dimension}', "
            f"value={self.value}, weight={self.weight})>"
        )
