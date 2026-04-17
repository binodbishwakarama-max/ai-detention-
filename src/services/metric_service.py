"""
Metric service — CRUD for evaluation metrics.

Manages both built-in metrics (seeded at startup) and custom per-org metrics.
"""

from __future__ import annotations

from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.error_handler import ConflictError, NotFoundError
from src.models.audit_log import AuditAction
from src.models.metric import Metric, MetricType
from src.services.audit_service import create_audit_log

logger = structlog.get_logger(__name__)

# ── Built-in Metric Definitions ─────────────────────────────
BUILTIN_METRICS = [
    {
        "name": "accuracy_exact_match",
        "display_name": "Exact Match Accuracy",
        "description": "Proportion of outputs that exactly match the expected output",
        "metric_type": MetricType.ACCURACY,
        "higher_is_better": True,
        "min_value": 0.0,
        "max_value": 1.0,
    },
    {
        "name": "f1_token",
        "display_name": "Token-level F1 Score",
        "description": "Harmonic mean of precision and recall at the token level",
        "metric_type": MetricType.F1,
        "higher_is_better": True,
        "min_value": 0.0,
        "max_value": 1.0,
    },
    {
        "name": "bleu_4",
        "display_name": "BLEU-4 Score",
        "description": "BiLingual Evaluation Understudy with 4-gram precision",
        "metric_type": MetricType.BLEU,
        "higher_is_better": True,
        "min_value": 0.0,
        "max_value": 1.0,
    },
    {
        "name": "rouge_l",
        "display_name": "ROUGE-L Score",
        "description": "Longest common subsequence based recall metric",
        "metric_type": MetricType.ROUGE,
        "higher_is_better": True,
        "min_value": 0.0,
        "max_value": 1.0,
    },
    {
        "name": "toxicity_score",
        "display_name": "Toxicity Score",
        "description": "Probability that the output contains toxic content (lower is better)",
        "metric_type": MetricType.TOXICITY,
        "higher_is_better": False,
        "min_value": 0.0,
        "max_value": 1.0,
    },
    {
        "name": "response_latency",
        "display_name": "Response Latency (ms)",
        "description": "Time taken for the model to generate a response",
        "metric_type": MetricType.LATENCY,
        "higher_is_better": False,
        "min_value": 0.0,
        "max_value": 60000.0,
    },
    {
        "name": "coherence_score",
        "display_name": "Coherence Score",
        "description": "Semantic coherence and logical consistency of the output",
        "metric_type": MetricType.COHERENCE,
        "higher_is_better": True,
        "min_value": 0.0,
        "max_value": 1.0,
    },
    {
        "name": "relevance_score",
        "display_name": "Relevance Score",
        "description": "How relevant the output is to the input prompt",
        "metric_type": MetricType.RELEVANCE,
        "higher_is_better": True,
        "min_value": 0.0,
        "max_value": 1.0,
    },
]


async def seed_builtin_metrics(db: AsyncSession) -> int:
    """
    Seed built-in metrics if they don't already exist.

    Called during application startup. Uses upsert-like logic:
    only creates metrics whose name doesn't already exist.
    Returns the number of metrics created.
    """
    created = 0
    for metric_def in BUILTIN_METRICS:
        existing = await db.execute(
            select(Metric).where(
                Metric.name == metric_def["name"],
                Metric.is_builtin == True,  # noqa: E712
                Metric.deleted_at.is_(None),
            )
        )
        if existing.scalar_one_or_none():
            continue

        metric = Metric(
            **metric_def,
            organization_id=None,  # built-in metrics are global
            is_builtin=True,
            computation_config={},
        )
        db.add(metric)
        created += 1

    if created:
        await db.flush()
        logger.info("metrics.seeded", count=created)

    return created


async def create_custom_metric(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    name: str,
    display_name: str,
    description: str | None = None,
    metric_type: MetricType = MetricType.CUSTOM,
    computation_config: dict | None = None,
    higher_is_better: bool = True,
    min_value: float = 0.0,
    max_value: float = 1.0,
    ip_address: str | None = None,
) -> Metric:
    """Create a custom metric scoped to an organization."""
    # Check for duplicate name within org
    existing = await db.execute(
        select(Metric).where(
            Metric.name == name,
            Metric.organization_id == org_id,
            Metric.deleted_at.is_(None),  # noqa: E712
        )
    )
    if existing.scalar_one_or_none():
        raise ConflictError(
            f"Metric with name '{name}' already exists in this organization"
        )

    metric = Metric(
        name=name,
        display_name=display_name,
        description=description,
        organization_id=org_id,
        metric_type=metric_type,
        computation_config=computation_config or {},
        higher_is_better=higher_is_better,
        min_value=min_value,
        max_value=max_value,
        is_builtin=False,
    )
    db.add(metric)
    await db.flush()

    await create_audit_log(
        db,
        action=AuditAction.CREATE,
        resource_type="metric",
        resource_id=str(metric.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )

    return metric


async def list_metrics(
    db: AsyncSession,
    *,
    org_id: UUID,
    page: int = 1,
    page_size: int = 50,
) -> tuple[list[Metric], int]:
    """
    List metrics available to an organization.

    Returns both built-in (global) metrics and custom org metrics.
    """
    from sqlalchemy import or_

    base_where = [
        or_(
            Metric.organization_id == org_id,
            Metric.is_builtin == True,  # noqa: E712
        ),
        Metric.deleted_at.is_(None),  # noqa: E712
    ]

    count_stmt = (
        select(func.count())
        .select_from(Metric)
        .where(*base_where)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Metric)
        .where(*base_where)
        .order_by(Metric.is_builtin.desc(), Metric.name)
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    metrics = list(result.scalars().all())

    return metrics, total


async def get_metric(
    db: AsyncSession,
    *,
    metric_id: UUID,
    org_id: UUID,
) -> Metric:
    """Fetch a metric by ID, accessible if built-in or org-scoped."""
    from sqlalchemy import or_

    result = await db.execute(
        select(Metric).where(
            Metric.id == metric_id,
            or_(
                Metric.organization_id == org_id,
                Metric.is_builtin == True,  # noqa: E712
            ),
            Metric.deleted_at.is_(None),  # noqa: E712
        )
    )
    metric = result.scalar_one_or_none()
    if not metric:
        raise NotFoundError("Metric", str(metric_id))
    return metric
