"""
Audit logging service.

Writes immutable audit log entries to the database. This service is used
by all other services and the audit middleware to record operations.

Design:
- Fire-and-forget: audit logging should never block or fail the main operation
- Raw INSERT: no ORM overhead for high-volume writes
- Error-suppressed: audit failures are logged but never raised
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.correlation import get_correlation_id
from src.models.audit_log import AuditAction, AuditLog

logger = structlog.get_logger(__name__)


async def create_audit_log(
    db: AsyncSession,
    *,
    action: AuditAction,
    resource_type: str,
    resource_id: str | None = None,
    organization_id: UUID | None = None,
    user_id: UUID | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    changes: dict | None = None,
    status: str = "success",
    detail: str | None = None,
) -> None:
    """
    Create an audit log entry.

    Uses raw INSERT for performance — no ORM overhead for high-volume writes.
    Errors are caught and logged but never raised to avoid disrupting
    the primary operation.
    """
    try:
        request_id = get_correlation_id()
        stmt = insert(AuditLog).values(
            timestamp=datetime.now(timezone.utc),
            organization_id=organization_id,
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            changes=changes,
            status=status,
            detail=detail,
        )
        await db.execute(stmt)
        # Note: commit is handled by the session context manager
    except Exception:
        # Audit logging must never crash the application
        logger.exception(
            "audit.write_failed",
            action=action.value,
            resource_type=resource_type,
            resource_id=str(resource_id) if resource_id else None,
        )
