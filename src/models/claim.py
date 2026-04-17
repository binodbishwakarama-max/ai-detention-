"""
Claim model — every individual claim extracted from a submission.

Claims are atomic statements extracted from pitch decks, websites,
or other submission materials. Each claim is individually categorized,
sourced, and can be cross-referenced against other claims for
contradiction detection.

Examples:
  "Revenue grew 300% YoY" (category: financials)
  "Team has 15 years combined ML experience" (category: team)
  "TAM is $50B" (category: market)
"""

from __future__ import annotations

import uuid

from sqlalchemy import Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel


class Claim(BaseModel):
    """An individual claim extracted from a submission's materials."""

    __tablename__ = "claims"
    __table_args__ = (
        # Composite index: all claims for a specific run
        Index(
            "ix_claims_run_active",
            "evaluation_run_id",
            postgresql_where="deleted_at IS NULL",
        ),
        # Index for category filtering within a run
        Index(
            "ix_claims_run_category_active",
            "evaluation_run_id",
            "category",
            postgresql_where="deleted_at IS NULL",
        ),
        # Index for org-level claim analytics
        Index(
            "ix_claims_org_active",
            "organization_id",
            postgresql_where="deleted_at IS NULL",
        ),
    )

    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"),
        nullable=False,
        doc="The evaluation run that extracted this claim",
    )
    submission_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        doc="Denormalized for direct submission-level queries",
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        doc="Denormalized org_id for RLS",
    )
    # Claim content
    claim_text: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        doc="The exact claim statement extracted",
    )
    category: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        doc="Claim category: 'financials', 'team', 'market', 'product', 'traction'",
    )
    source_reference: Mapped[str | None] = mapped_column(
        String(500),
        nullable=True,
        doc="Where in the submission this claim was found (page, section, URL)",
    )
    # Scoring
    confidence_score: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        doc="AI confidence in extraction accuracy (0.0-1.0)",
    )
    verification_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="unverified",
        doc="Verification state: 'unverified', 'verified', 'disputed', 'false'",
    )
    # Extended data
    evidence: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Supporting evidence: {sources: [], reasoning: '...'}",
    )
    claim_metadata: Mapped[dict] = mapped_column(
        "metadata",
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Extra metadata: {extraction_method, model_used, ...}",
    )

    # ── Relationships ─────────────────────────────────────
    evaluation_run = relationship("EvaluationRun", back_populates="claims", lazy="joined")
    submission = relationship("Submission", lazy="noload")
    organization = relationship("Organization", lazy="noload")

    # Contradictions where this claim is claim_a or claim_b
    contradictions_as_a = relationship(
        "Contradiction",
        foreign_keys="Contradiction.claim_a_id",
        back_populates="claim_a",
        lazy="noload",
    )
    contradictions_as_b = relationship(
        "Contradiction",
        foreign_keys="Contradiction.claim_b_id",
        back_populates="claim_b",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return (
            f"<Claim(id={self.id}, category='{self.category}', "
            f"status='{self.verification_status}')>"
        )
