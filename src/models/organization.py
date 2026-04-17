"""
Organization model — the multi-tenancy root entity.

Every piece of data in the system belongs to an organization.
Row-Level Security (RLS) policies on every table use org_id to
ensure strict data isolation at the PostgreSQL level, not just
the application level.
"""

from __future__ import annotations

import enum

from sqlalchemy import Index, Integer, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel


class PlanTier(str, enum.Enum):
    """Subscription plan tiers with increasing resource limits."""
    FREE = "free"
    PRO = "pro"
    ENTERPRISE = "enterprise"


class Organization(BaseModel):
    """Multi-tenant root entity. All data is scoped to an organization."""

    __tablename__ = "organizations"
    __table_args__ = (
        # Partial index: only active orgs (soft-delete filter)
        Index(
            "ix_organizations_slug_active",
            "slug",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
    )

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Human-readable organization name",
    )
    slug: Mapped[str] = mapped_column(
        String(63),
        nullable=False,
        doc="URL-safe identifier, used in API paths and subdomains",
    )
    plan_tier: Mapped[PlanTier] = mapped_column(
        SAEnum(PlanTier, name="plan_tier", create_constraint=True, values_callable=lambda obj: [e.value for e in obj]),
        nullable=False,
        default=PlanTier.FREE,
        doc="Current subscription plan",
    )
    rate_limit_per_minute: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=100,
        doc="Maximum API requests per minute for this organization",
    )
    max_concurrent_evaluations: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=10,
        doc="Maximum evaluations running simultaneously",
    )
    settings: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default="{}",
        doc="Org-specific settings (webhook defaults, notification prefs, etc.)",
    )

    # ── Relationships ─────────────────────────────────────
    users = relationship("User", back_populates="organization", lazy="noload")
    submissions = relationship("Submission", back_populates="organization", lazy="noload")
    datasets = relationship("Dataset", back_populates="organization", lazy="noload")
    api_keys = relationship("ApiKey", back_populates="organization", lazy="noload")

    def __repr__(self) -> str:
        return f"<Organization(id={self.id}, slug='{self.slug}', plan='{self.plan_tier.value}')>"
