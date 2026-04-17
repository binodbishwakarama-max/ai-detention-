"""
Metric model — evaluation measurement definitions.

Supports both built-in metrics (shared across all orgs) and custom
metrics (scoped to a single org). Built-in metrics include:
- ACCURACY: exact match or fuzzy match
- F1: token-level F1 score
- BLEU: machine translation quality
- ROUGE: summarization quality
- TOXICITY: content safety score
- LATENCY: response time measurement

Custom metrics use computation_config to define their evaluation logic.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Float, ForeignKey, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel


class MetricType(str, enum.Enum):
    """Built-in metric types."""

    ACCURACY = "accuracy"
    F1 = "f1"
    BLEU = "bleu"
    ROUGE = "rouge"
    TOXICITY = "toxicity"
    LATENCY = "latency"
    COHERENCE = "coherence"
    RELEVANCE = "relevance"
    CUSTOM = "custom"


class Metric(BaseModel):
    """Evaluation metric definition — built-in or custom per org."""

    __tablename__ = "metrics"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Internal metric name (e.g., 'accuracy_exact_match')",
    )
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Human-readable name (e.g., 'Exact Match Accuracy')",
    )
    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
        doc="Description of what this metric measures and how to interpret scores",
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
        doc="NULL for built-in metrics, org ID for custom metrics",
    )
    metric_type: Mapped[MetricType] = mapped_column(
        SAEnum(MetricType, name="metric_type", create_constraint=True),
        nullable=False,
        doc="The type of metric computation",
    )
    computation_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Custom computation parameters: {method, threshold, tokenizer, ...}",
    )
    higher_is_better: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Score direction — True: higher=better, False: lower=better",
    )
    min_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=0.0,
        doc="Minimum possible score",
    )
    max_value: Mapped[float] = mapped_column(
        Float,
        nullable=False,
        default=1.0,
        doc="Maximum possible score",
    )
    is_builtin: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether this is a system-provided metric",
    )

    # ── Relationships ─────────────────────────────────────
    organization = relationship("Organization", lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<Metric(id={self.id}, name='{self.name}', "
            f"type='{self.metric_type.value}')>"
        )
