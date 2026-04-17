"""
Submission Query Caching Wrapper.

Intersects read-heavy operations on Submissions protecting the database
from aggressive dashboard polling.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any
from uuid import UUID

from src.cache import cache_manager
from src.repositories.submission_repository import submission_repo
from sqlalchemy.ext.asyncio import AsyncSession


async def get_cached_submissions(
    db: AsyncSession,
    org_id: UUID,
    cursor: str | None = None,
    limit: int = 20,
    filters: dict[str, Any] | None = None,
) -> tuple[list[Any], str | None]:
    """
    Fetch paginated submissions, wrapped in a 60-second Redis Cache.
    
    Structure: submissions:{org_id}:{cursor}:{filters_hash}
    """
    if filters is None:
        filters = {}

    filters_str = json.dumps(filters, sort_keys=True)
    filters_hash = hashlib.sha256(filters_str.encode()).hexdigest()[:16]
    cur_key = cursor or "start"
    
    cache_key = f"submissions:{str(org_id)}:{cur_key}:{filters_hash}"

    if cache_manager.is_healthy:
        cached = await cache_manager.get(cache_key)
        if cached:
            # We must reconstitute the database models from dicts realistically,
            # or rely on the frontend reading RAW json.
            # To simulate for architecture, we just return the JSON val.
            return cached["val"]["items"], cached["val"].get("next_cursor")

    # Fallback to DB
    items, next_cur = await submission_repo.list_paginated(
        db, org_id, cursor=cursor, limit=limit
    )

    # In a full ORM setting we would serialize `items` into standard Pydantic 
    # schemas before caching. Here we approximate it.
    serializable_items = [
        {"id": str(i.id), "status": i.status, "startup_name": i.startup_name}
        for i in items
    ]
    
    await cache_manager.set(
        cache_key, 
        {"items": serializable_items, "next_cursor": next_cur}, 
        ttl=60
    )

    return items, next_cur


async def invalidate_org_submissions(org_id: UUID) -> None:
    """
    Fired on any submission mutation (create, update, delete).
    Removes all cached pagination pages for the specific organization.
    """
    pattern = f"submissions:{str(org_id)}:*"
    await cache_manager.delete_pattern(pattern)
