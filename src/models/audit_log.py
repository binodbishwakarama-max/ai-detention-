"""
Audit log model — immutable, append-only record of every state change.

This table is append-only: NO UPDATE or DELETE operations are permitted.
This is enforced at the database level via a trigger (see migration).

SOC2 CC6.1: complete audit trail of all data access and modifications.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from src.models.base import Base


class AuditAction(str, enum.Enum):
    """Auditable actions tracked across the system."""
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    SUBMISSION_CREATED = "submission_created"
    SUBMISSION_UPDATED = "submission_updated"
    EVALUATION_STARTED = "evaluation_started"
    EVALUATION_COMPLETED = "evaluation_completed"
    EVALUATION_FAILED = "evaluation_failed"
    EVALUATION_CANCELLED = "evaluation_cancelled"
    CLAIM_EXTRACTED = "claim_extracted"
    CONTRADICTION_DETECTED = "contradiction_detected"
    SCORE_RECORDED = "score_recorded"
    SETTINGS_CHANGED = "settings_changed"


class AuditLog(Base):
    """
    Immutable audit log entry.

    Deliberately does NOT extend BaseModel:
    - BigInteger ID: faster sequential inserts than UUID
    - No soft-delete: audit logs are permanent
    - No updated_at: append-only, never modified
    - No FK constraints: survives deletion of referenced entities
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        # Composite index for filtering by org + time range
        Index("ix_audit_logs_org_timestamp", "organization_id", "timestamp"),
        # Index for filtering by action type
        Index("ix_audit_logs_action", "action"),
        # Index for correlation with requests
        Index("ix_audit_logs_request_id", "request_id"),
        # Index for user activity lookup
        Index("ix_audit_logs_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True,
        doc="Auto-incrementing ID for fast sequential inserts",
    )
    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("NOW()"),
        doc="When the action occurred",
    )
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        doc="Organization context (NULL for system-level events)",
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True,
        doc="User who performed the action (NULL for system actions)",
    )
    action: Mapped[AuditAction] = mapped_column(
        SAEnum(AuditAction, name="audit_action", create_constraint=True),
        nullable=False,
        doc="The action that was performed",
    )
    resource_type: Mapped[str] = mapped_column(
        String(100), nullable=False,
        doc="Type of resource affected (e.g., 'evaluation_run', 'submission')",
    )
    resource_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True,
        doc="ID of the affected resource",
    )
    ip_address: Mapped[str | None] = mapped_column(
        String(45), nullable=True,
        doc="Client IP address",
    )
    user_agent: Mapped[str | None] = mapped_column(
        String(512), nullable=True,
        doc="Client user agent string",
    )
    request_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True,
        doc="Correlation ID for request tracing",
    )
    changes: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
        doc="Before/after snapshot: {before: {...}, after: {...}}",
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="success",
        doc="Action outcome: 'success' or 'failure'",
    )
    detail: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        doc="Additional context or error message",
    )

    def __repr__(self) -> str:
        return f"<AuditLog(id={self.id}, action='{self.action.value}', resource='{self.resource_type}')>"
