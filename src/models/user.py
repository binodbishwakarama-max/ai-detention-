"""
User model — authenticated entity within an organization.

Roles:
  ADMIN  — full access, manage org settings and users
  JUDGE  — create/run evaluations, score submissions
  VIEWER — read-only access to results and reports

Security:
- Passwords stored as bcrypt hashes (see src/security.py)
- Failed login attempts tracked for account lockout (5 max)
- last_login_at updated on every successful authentication
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.models.base import BaseModel


class UserRole(str, enum.Enum):
    """User roles with hierarchical permissions."""
    ADMIN = "admin"
    JUDGE = "judge"
    VIEWER = "viewer"


# Role hierarchy for "at least" permission checks
ROLE_HIERARCHY: dict[UserRole, int] = {
    UserRole.VIEWER: 1,
    UserRole.JUDGE: 2,
    UserRole.ADMIN: 3,
}


class User(BaseModel):
    """Authenticated user within an organization."""

    __tablename__ = "users"
    __table_args__ = (
        # Partial unique index: email must be unique among active users
        Index(
            "ix_users_email_active",
            "email",
            unique=True,
            postgresql_where="deleted_at IS NULL",
        ),
        # Index for org-scoped user lookups
        Index(
            "ix_users_org_active",
            "organization_id",
            postgresql_where="deleted_at IS NULL",
        ),
    )

    email: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Unique email address, used for login",
    )
    hashed_password: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="bcrypt-hashed password",
    )
    full_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        doc="Display name",
    )
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="user_role", create_constraint=True),
        nullable=False,
        default=UserRole.VIEWER,
        doc="RBAC role within the organization",
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        doc="Parent organization FK — every user belongs to exactly one org",
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        doc="Account active flag — deactivated users cannot authenticate",
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp of last successful login",
    )
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        doc="Consecutive failed login attempts — lockout after 5",
    )

    # ── Relationships ─────────────────────────────────────
    organization = relationship("Organization", back_populates="users", lazy="joined")

    # ── Constants ─────────────────────────────────────────
    MAX_FAILED_ATTEMPTS = 5

    @property
    def is_locked(self) -> bool:
        """Account is locked after MAX_FAILED_ATTEMPTS consecutive failures."""
        return self.failed_login_attempts >= self.MAX_FAILED_ATTEMPTS

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email='{self.email}', role='{self.role.value}')>"
