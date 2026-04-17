"""Metric schemas."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, Field

from src.models.metric import MetricType
from src.schemas.common import TimestampSchema


class MetricCreate(BaseModel):
    """Schema for creating a custom metric."""

    name: str = Field(min_length=1, max_length=255)
    display_name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    metric_type: MetricType = MetricType.CUSTOM
    computation_config: dict = Field(default_factory=dict)
    higher_is_better: bool = True
    min_value: float = 0.0
    max_value: float = 1.0


class MetricUpdate(BaseModel):
    """Schema for updating a metric."""

    display_name: str | None = None
    description: str | None = None
    computation_config: dict | None = None
    higher_is_better: bool | None = None
    min_value: float | None = None
    max_value: float | None = None


class MetricResponse(TimestampSchema):
    """Metric response."""

    id: UUID
    name: str
    display_name: str
    description: str | None
    organization_id: UUID | None
    metric_type: MetricType
    computation_config: dict
    higher_is_better: bool
    min_value: float
    max_value: float
    is_builtin: bool
