"""
API Key model — programmatic access credentials.

Each API key is:
- Scoped: limited to specific actions (read, write, admin)
- Revocable: can be instantly invalidated without rotating secrets
- Audited: every use is logged with timestamp and IP
- Expirable: optional TTL for time-limited access

Only the SHA-256 hash is stored. The raw key is shown once at creation.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel


class ApiKey(BaseModel):
    """Programmatic access credential — scoped, revocable, expirable."""

    __tablename__ = "api_keys"

    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Human-readable name for this key (e.g., 'CI Pipeline')",
    )
    key_hash: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        doc="SHA-256 hash of the raw API key — used for authentication lookups",
    )
    key_prefix: Mapped[str] = mapped_column(
        String(11),
        nullable=False,
        doc="First 11 chars of the key (e.g., 'ev_dk3n...') for display in UI",
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="User who created this key",
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Organization this key belongs to",
    )
    scopes: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        server_default="[]",
        doc="Permission scopes: ['evaluations:read', 'evaluations:write', ...]",
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Optional expiration timestamp — NULL means never expires",
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of last API call using this key",
    )
    is_revoked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        doc="Whether this key has been revoked",
    )

    # ── Relationships ─────────────────────────────────────
    user = relationship("User", back_populates="api_keys", lazy="joined")
    organization = relationship(
        "Organization", back_populates="api_keys", lazy="joined"
    )

    @property
    def is_valid(self) -> bool:
        """Check if the key is neither revoked nor expired."""
        if self.is_revoked:
            return False
        if self.expires_at and self.expires_at < datetime.now(timezone.utc):
            return False
        return True

    def __repr__(self) -> str:
        return (
            f"<ApiKey(id={self.id}, prefix='{self.key_prefix}', "
            f"revoked={self.is_revoked})>"
        )
