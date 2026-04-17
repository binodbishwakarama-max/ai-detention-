"""
Evaluation service — CRUD for pipeline configs and run lifecycle management.

EvaluationConfig CRUD: create, get, list, update, delete pipeline templates.
Run lifecycle: get, list, cancel evaluation runs.
Run creation is handled via submission_service.trigger_evaluation().
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.error_handler import (
    ConflictError,
    NotFoundError,
)
from src.models.audit_log import AuditAction
from src.models.evaluation import (
    EvaluationConfig,
    EvaluationRun,
    RunStatus,
)
from src.services.audit_service import create_audit_log
from src.services.cache_service import cache_delete, cache_get

logger = structlog.get_logger(__name__)


# ── Evaluation Config CRUD ───────────────────────────────


async def create_evaluation_config(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    name: str,
    description: str | None = None,
    pipeline_config: dict | None = None,
    webhook_url: str | None = None,
    is_template: bool = False,
    ip_address: str | None = None,
) -> EvaluationConfig:
    """Create a new pipeline configuration template."""
    config = EvaluationConfig(
        name=name,
        description=description,
        organization_id=org_id,
        created_by_id=user_id,
        pipeline_config=pipeline_config or {},
        webhook_url=webhook_url,
        is_template=is_template,
    )
    db.add(config)
    await db.flush()

    await create_audit_log(
        db,
        action=AuditAction.CREATE,
        resource_type="evaluation_config",
        resource_id=str(config.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )

    logger.info(
        "evaluation.config_created",
        config_id=str(config.id),
        org_id=str(org_id),
    )
    return config


async def get_evaluation_config(
    db: AsyncSession,
    *,
    config_id: UUID,
    org_id: UUID,
) -> EvaluationConfig:
    """Fetch an evaluation config by ID, scoped to an organization."""
    result = await db.execute(
        select(EvaluationConfig).where(
            EvaluationConfig.id == config_id,
            EvaluationConfig.organization_id == org_id,
            EvaluationConfig.is_deleted == False,  # noqa: E712
        )
    )
    config = result.scalar_one_or_none()
    if not config:
        raise NotFoundError("Evaluation config", str(config_id))

    return config


async def list_evaluation_configs(
    db: AsyncSession,
    *,
    org_id: UUID,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[EvaluationConfig], int]:
    """List evaluation configs for an organization with pagination."""
    count_stmt = (
        select(func.count())
        .select_from(EvaluationConfig)
        .where(
            EvaluationConfig.organization_id == org_id,
            EvaluationConfig.is_deleted == False,  # noqa: E712
        )
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(EvaluationConfig)
        .where(
            EvaluationConfig.organization_id == org_id,
            EvaluationConfig.is_deleted == False,  # noqa: E712
        )
        .order_by(EvaluationConfig.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    configs = list(result.scalars().all())

    return configs, total


async def update_evaluation_config(
    db: AsyncSession,
    *,
    config_id: UUID,
    org_id: UUID,
    user_id: UUID,
    updates: dict,
    ip_address: str | None = None,
) -> EvaluationConfig:
    """Update an evaluation config, incrementing its version."""
    config = await get_evaluation_config(
        db, config_id=config_id, org_id=org_id
    )

    before = {"name": config.name, "version": config.version}

    for field, value in updates.items():
        if value is not None and hasattr(config, field):
            setattr(config, field, value)

    config.version += 1
    await db.flush()

    await cache_delete("eval_config", str(config_id))

    await create_audit_log(
        db,
        action=AuditAction.UPDATE,
        resource_type="evaluation_config",
        resource_id=str(config.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
        changes={"before": before, "after": {"name": config.name, "version": config.version}},
    )

    return config


async def delete_evaluation_config(
    db: AsyncSession,
    *,
    config_id: UUID,
    org_id: UUID,
    user_id: UUID,
    ip_address: str | None = None,
) -> None:
    """Soft-delete an evaluation config."""
    config = await get_evaluation_config(
        db, config_id=config_id, org_id=org_id
    )
    config.soft_delete()
    await db.flush()

    await cache_delete("eval_config", str(config_id))

    await create_audit_log(
        db,
        action=AuditAction.DELETE,
        resource_type="evaluation_config",
        resource_id=str(config.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )


# ── Evaluation Run Lifecycle ─────────────────────────────


async def get_evaluation_run(
    db: AsyncSession,
    *,
    run_id: UUID,
    org_id: UUID,
) -> EvaluationRun:
    """Fetch an evaluation run by ID, scoped to an organization."""
    result = await db.execute(
        select(EvaluationRun).where(
            EvaluationRun.id == run_id,
            EvaluationRun.organization_id == org_id,
            EvaluationRun.is_deleted == False,  # noqa: E712
        )
    )
    run = result.scalar_one_or_none()
    if not run:
        raise NotFoundError("Evaluation run", str(run_id))
    return run


async def list_evaluation_runs(
    db: AsyncSession,
    *,
    org_id: UUID,
    submission_id: UUID | None = None,
    config_id: UUID | None = None,
    status_filter: RunStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[EvaluationRun], int]:
    """List evaluation runs with optional filtering and pagination."""
    base_where = [
        EvaluationRun.organization_id == org_id,
        EvaluationRun.is_deleted == False,  # noqa: E712
    ]
    if submission_id:
        base_where.append(EvaluationRun.submission_id == submission_id)
    if config_id:
        base_where.append(EvaluationRun.config_id == config_id)
    if status_filter:
        base_where.append(EvaluationRun.status == status_filter)

    count_stmt = (
        select(func.count())
        .select_from(EvaluationRun)
        .where(*base_where)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(EvaluationRun)
        .where(*base_where)
        .order_by(EvaluationRun.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    runs = list(result.scalars().all())

    return runs, total


async def cancel_evaluation_run(
    db: AsyncSession,
    *,
    run_id: UUID,
    org_id: UUID,
    user_id: UUID,
    ip_address: str | None = None,
) -> EvaluationRun:
    """Cancel a running or pending evaluation."""
    run = await get_evaluation_run(db, run_id=run_id, org_id=org_id)

    if run.is_terminal:
        raise ConflictError(
            f"Cannot cancel run in '{run.status.value}' state"
        )

    # Revoke Celery task
    if run.celery_task_id:
        from src.workers.celery_app import celery_app

        celery_app.control.revoke(
            run.celery_task_id, terminate=True, signal="SIGKILL"
        )

    run.status = RunStatus.CANCELLED
    run.completed_at = datetime.now(timezone.utc)
    await db.flush()

    await create_audit_log(
        db,
        action=AuditAction.EVALUATION_CANCELLED,
        resource_type="evaluation_run",
        resource_id=str(run.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )

    logger.info("evaluation.run_cancelled", run_id=str(run.id))
    return run
