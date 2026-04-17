"""
Contradiction model — detected conflicts between two claims.

When an evaluation identifies that claim A and claim B are mutually
contradictory, a Contradiction record is created linking the two.

Examples:
  Claim A: "Revenue grew 300% YoY"
  Claim B: "We are pre-revenue"
  → severity: 1.0 (critical contradiction)

  Claim A: "Team of 50 engineers"
  Claim B: "Total team size is 20"
  → severity: 0.8 (significant inconsistency)
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel


class Contradiction(BaseModel):
    """Detected conflict between two claims within an evaluation."""

    __tablename__ = "contradictions"
    __table_args__ = (
        # Index: all contradictions for a run
        Index(
            "ix_contradictions_run_active",
            "evaluation_run_id",
            postgresql_where="deleted_at IS NULL",
        ),
        # Index: org-level analytics
        Index(
            "ix_contradictions_org_active",
            "organization_id",
            postgresql_where="deleted_at IS NULL",
        ),
    )

    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        doc="The evaluation run that detected this contradiction",
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        doc="Denormalized org_id for RLS",
    )
    claim_a_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        doc="First claim in the contradicting pair",
    )
    claim_b_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("claims.id", ondelete="CASCADE"),
        nullable=False,
        doc="Second claim in the contradicting pair",
    )
    contradiction_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Type: 'direct', 'numerical', 'temporal', 'logical'",
    )
    severity: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        doc="Severity score (0.0-1.0): 1.0 means critical contradiction",
    )
    explanation: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="Human-readable explanation of why these claims conflict",
    )
    # Extended data
    evidence: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Supporting evidence and reasoning",
    )

    # ── Relationships ─────────────────────────────────────
    evaluation_run = relationship("EvaluationRun", back_populates="contradictions", lazy="joined")
    claim_a = relationship(
        "Claim",
        foreign_keys=[claim_a_id],
        back_populates="contradictions_as_a",
        lazy="joined",
    )
    claim_b = relationship(
        "Claim",
        foreign_keys=[claim_b_id],
        back_populates="contradictions_as_b",
        lazy="joined",
    )
    organization = relationship("Organization", lazy="noload")

    def __repr__(self) -> str:
        return (
            f"<Contradiction(id={self.id}, type='{self.contradiction_type}', "
            f"severity={self.severity})>"
        )
