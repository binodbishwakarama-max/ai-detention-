"""
Pagination utilities for consistent paginated responses.

Provides helper functions to build PaginatedResponse objects
from SQLAlchemy query results.
"""

from __future__ import annotations

import math
from typing import Any, TypeVar

from src.schemas.common import PaginatedResponse, PaginationParams

T = TypeVar("T")


def build_paginated_response(
    items: list[Any],
    total: int,
    params: PaginationParams,
) -> dict:
    """
    Build a paginated response dict from query results.

    Args:
        items: List of items for the current page
        total: Total number of items matching the query
        params: Pagination parameters (page, page_size)

    Returns:
        Dict matching PaginatedResponse schema
    """
    total_pages = math.ceil(total / params.page_size) if total > 0 else 0

    return {
        "items": items,
        "total": total,
        "page": params.page,
        "page_size": params.page_size,
        "total_pages": total_pages,
        "has_next": params.page < total_pages,
        "has_prev": params.page > 1,
    }


def paginate_list(
    items: list[Any],
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """
    Paginate an in-memory list.

    Useful for small collections that don't warrant a database query
    with OFFSET/LIMIT.
    """
    total = len(items)
    total_pages = math.ceil(total / page_size) if total > 0 else 0
    start = (page - 1) * page_size
    end = start + page_size

    return {
        "items": items[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_prev": page > 1,
    }
