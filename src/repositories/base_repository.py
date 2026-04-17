"""
Base repository — generic CRUD operations for all domain models.

Design decisions:
- Generic base: eliminates boilerplate across all repositories
- Always filters deleted_at IS NULL unless include_deleted=True
- All writes happen inside the caller's transaction (no autonomous commits)
- selectinload/joinedload specified per-method to prevent N+1 queries
- Pagination is offset-based with consistent counting
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Generic, Sequence, TypeVar
from uuid import UUID

from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from src.models.base import BaseModel

T = TypeVar("T", bound=BaseModel)


class BaseRepository(Generic[T]):
    """
    Generic repository providing CRUD operations.

    All methods respect soft-delete by default.
    All methods accept an AsyncSession — they never create their own
    transactions, leaving that to the service layer.
    """

    def __init__(self, model: type[T]):
        self.model = model

    # ── Read ─────────────────────────────────────────────

    def _base_query(
        self,
        *,
        include_deleted: bool = False,
    ) -> Select:
        """Base query with optional soft-delete filtering."""
        stmt = select(self.model)
        if not include_deleted:
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return stmt

    async def get_by_id(
        self,
        db: AsyncSession,
        entity_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> T | None:
        """Fetch a single entity by primary key."""
        stmt = self._base_query(include_deleted=include_deleted).where(
            self.model.id == entity_id
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_and_org(
        self,
        db: AsyncSession,
        entity_id: UUID,
        org_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> T | None:
        """Fetch a single entity scoped to an organization."""
        stmt = self._base_query(include_deleted=include_deleted).where(
            self.model.id == entity_id,
            self.model.organization_id == org_id,  # type: ignore[attr-defined]
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_org(
        self,
        db: AsyncSession,
        org_id: UUID,
        *,
        page: int = 1,
        page_size: int = 20,
        order_by: InstrumentedAttribute | None = None,
        include_deleted: bool = False,
        extra_filters: list | None = None,
    ) -> tuple[list[T], int]:
        """
        List entities for an organization with pagination.

        Returns:
            Tuple of (items, total_count)
        """
        # Build base with filters
        conditions = [
            self.model.organization_id == org_id,  # type: ignore[attr-defined]
        ]
        if not include_deleted:
            conditions.append(self.model.deleted_at.is_(None))
        if extra_filters:
            conditions.extend(extra_filters)

        # Count total
        count_stmt = (
            select(func.count())
            .select_from(self.model)
            .where(*conditions)
        )
        total = (await db.execute(count_stmt)).scalar() or 0

        # Fetch page
        sort_col = order_by if order_by is not None else self.model.created_at.desc()
        stmt = (
            select(self.model)
            .where(*conditions)
            .order_by(sort_col)
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await db.execute(stmt)
        items = list(result.scalars().all())

        return items, total

    async def exists(
        self,
        db: AsyncSession,
        entity_id: UUID,
        *,
        org_id: UUID | None = None,
    ) -> bool:
        """Check if an entity exists (fast, no data returned)."""
        conditions = [
            self.model.id == entity_id,
            self.model.deleted_at.is_(None),
        ]
        if org_id is not None:
            conditions.append(
                self.model.organization_id == org_id  # type: ignore[attr-defined]
            )
        stmt = select(func.count()).select_from(self.model).where(*conditions)
        count = (await db.execute(stmt)).scalar() or 0
        return count > 0

    # ── Write ────────────────────────────────────────────

    async def create(self, db: AsyncSession, entity: T) -> T:
        """Add a new entity to the session."""
        db.add(entity)
        await db.flush()  # get the generated ID without committing
        return entity

    async def create_many(self, db: AsyncSession, entities: list[T]) -> list[T]:
        """Add multiple entities in a single flush."""
        db.add_all(entities)
        await db.flush()
        return entities

    async def soft_delete(
        self,
        db: AsyncSession,
        entity_id: UUID,
        *,
        org_id: UUID | None = None,
    ) -> bool:
        """
        Soft-delete an entity by setting deleted_at.

        Returns True if the entity was found and deleted.
        """
        conditions = [
            self.model.id == entity_id,
            self.model.deleted_at.is_(None),
        ]
        if org_id is not None:
            conditions.append(
                self.model.organization_id == org_id  # type: ignore[attr-defined]
            )

        stmt = (
            update(self.model)
            .where(*conditions)
            .values(deleted_at=datetime.now(timezone.utc))
        )
        result = await db.execute(stmt)
        return result.rowcount > 0

    async def hard_delete_expired(
        self,
        db: AsyncSession,
        cutoff: datetime,
    ) -> int:
        """
        Permanently delete records that were soft-deleted before cutoff.

        GDPR Article 17: data must be fully removed within retention period.
        """
        stmt = delete(self.model).where(
            self.model.deleted_at.isnot(None),
            self.model.deleted_at < cutoff,
        )
        result = await db.execute(stmt)
        return result.rowcount
