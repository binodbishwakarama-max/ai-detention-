"""
Audit log repository — append-only data access.

This repository intentionally exposes ONLY:
- create (insert)
- list/query (select)

It does NOT expose update or delete methods.
The database trigger (see migration) also prevents UPDATE/DELETE.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import insert, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.audit_log import AuditAction, AuditLog


class AuditLogRepository:
    """
    Append-only repository for audit logs.

    Does NOT extend BaseRepository — audit logs are intentionally
    different (BigInteger PK, no soft-delete, no update, no delete).
    """

    async def create(
        self,
        db: AsyncSession,
        *,
        action: AuditAction,
        resource_type: str,
        resource_id: str | None = None,
        organization_id: UUID | None = None,
        user_id: UUID | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        changes: dict | None = None,
        status: str = "success",
        detail: str | None = None,
    ) -> None:
        """
        Insert an audit log entry.

        Uses raw INSERT for performance: no ORM overhead on high-volume writes.
        Errors are caught and logged but never raised — audit logging must
        never crash the application.
        """
        import structlog
        logger = structlog.get_logger(__name__)

        try:
            stmt = insert(AuditLog).values(
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                organization_id=organization_id,
                user_id=user_id,
                ip_address=ip_address,
                user_agent=user_agent,
                request_id=request_id,
                changes=changes,
                status=status,
                detail=detail,
            )
            await db.execute(stmt)
        except Exception:
            logger.exception(
                "audit.write_failed",
                action=action.value,
                resource_type=resource_type,
            )

    async def list_by_org(
        self,
        db: AsyncSession,
        org_id: UUID,
        *,
        page: int = 1,
        page_size: int = 50,
        action_filter: AuditAction | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> tuple[list[AuditLog], int]:
        """Query audit logs for an organization with time range filtering."""
        conditions = [AuditLog.organization_id == org_id]
        if action_filter:
            conditions.append(AuditLog.action == action_filter)
        if start_time:
            conditions.append(AuditLog.timestamp >= start_time)
        if end_time:
            conditions.append(AuditLog.timestamp <= end_time)

        # Count
        count_stmt = (
            select(func.count()).select_from(AuditLog).where(*conditions)
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        # Fetch
        stmt = (
            select(AuditLog)
            .where(*conditions)
            .order_by(AuditLog.timestamp.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def list_by_resource(
        self,
        db: AsyncSession,
        resource_type: str,
        resource_id: str,
    ) -> list[AuditLog]:
        """Get the complete audit trail for a specific resource."""
        stmt = (
            select(AuditLog)
            .where(
                AuditLog.resource_type == resource_type,
                AuditLog.resource_id == resource_id,
            )
            .order_by(AuditLog.timestamp.asc())
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


# Singleton instance
audit_log_repo = AuditLogRepository()
