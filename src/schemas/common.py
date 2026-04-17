"""
Common schema types shared across the API.

Conventions:
- All schemas use Pydantic v2 with from_attributes=True for ORM compatibility.
- UUIDs are serialized as strings in JSON responses.
- Timestamps use ISO 8601 format with timezone.
- Pagination follows offset-based pattern with consistent metadata.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class BaseSchema(BaseModel):
    """Base schema with ORM mode enabled."""

    model_config = ConfigDict(
        from_attributes=True,
        populate_by_name=True,
    )


class TimestampSchema(BaseSchema):
    """Mixin schema for created/updated timestamps."""

    created_at: datetime
    updated_at: datetime


class PaginationParams(BaseModel):
    """Query parameters for paginated endpoints."""

    page: int = Field(default=1, ge=1, description="Page number (1-indexed)")
    page_size: int = Field(
        default=20, ge=1, le=100, description="Items per page"
    )

    @property
    def offset(self) -> int:
        return (self.page - 1) * self.page_size


class PaginatedResponse(BaseSchema, Generic[T]):
    """Standard paginated response envelope."""

    items: list[T]
    total: int = Field(description="Total number of items matching the query")
    page: int = Field(description="Current page number")
    page_size: int = Field(description="Items per page")
    total_pages: int = Field(description="Total number of pages")
    has_next: bool = Field(description="Whether there is a next page")
    has_prev: bool = Field(description="Whether there is a previous page")


class ErrorResponse(BaseSchema):
    """Standard error response format."""

    error: str = Field(description="Error type identifier")
    message: str = Field(description="Human-readable error message")
    detail: Any | None = Field(
        default=None, description="Additional error details"
    )
    request_id: str | None = Field(
        default=None, description="Correlation ID for support"
    )


class HealthResponse(BaseSchema):
    """Health check response."""

    status: str = Field(description="Overall health status")
    version: str = Field(description="Application version")
    environment: str = Field(description="Current environment")
    checks: dict[str, bool] = Field(
        description="Individual service health checks"
    )


class MessageResponse(BaseSchema):
    """Simple message response."""

    message: str
