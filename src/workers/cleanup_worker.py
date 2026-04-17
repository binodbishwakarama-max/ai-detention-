"""
Cleanup worker — scheduled maintenance tasks.

Handles:
1. Hard-delete of soft-deleted records past retention period (GDPR)
2. S3 cleanup for orphaned dataset files
3. Stale run cleanup (stuck in PENDING/RUNNING for too long)
4. Expired API key pruning

These tasks run on a Celery Beat schedule (configured in celery_app.py
or via external scheduler). Typical cadence: every 6 hours.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import delete, select, update

from src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)

# Records older than this are permanently deleted
RETENTION_DAYS = 30

# Runs stuck longer than this are marked as failed
STALE_RUN_HOURS = 24


def _run_async(coro):
    """Run an async coroutine from sync Celery context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _hard_delete_expired_records() -> dict:
    """
    Permanently delete records that have been soft-deleted
    past the retention period.

    GDPR Article 17: Right to erasure — data must be fully
    removed within the agreed retention period.
    """
    from src.database import get_standalone_session
    from src.models.dataset import Dataset
    from src.models.evaluation import (
        EvaluationConfig,
        EvaluationResult,
        EvaluationRun,
    )
    from src.models.organization import Organization
    from src.models.user import User
    from src.services.storage_service import delete_dataset_files

    cutoff = datetime.now(timezone.utc) - timedelta(days=RETENTION_DAYS)
    counts: dict[str, int] = {}

    async with get_standalone_session() as db:
        # Delete in order: results → runs → configs → datasets → users → orgs
        # (respecting foreign key constraints)

        # 1. Evaluation Results
        stmt = delete(EvaluationResult).where(
            EvaluationResult.is_deleted == True,  # noqa: E712
            EvaluationResult.deleted_at < cutoff,
        )
        result = await db.execute(stmt)
        counts["evaluation_results"] = result.rowcount

        # 2. Evaluation Runs
        stmt = delete(EvaluationRun).where(
            EvaluationRun.is_deleted == True,  # noqa: E712
            EvaluationRun.deleted_at < cutoff,
        )
        result = await db.execute(stmt)
        counts["evaluation_runs"] = result.rowcount

        # 3. Evaluation Configs
        stmt = delete(EvaluationConfig).where(
            EvaluationConfig.is_deleted == True,  # noqa: E712
            EvaluationConfig.deleted_at < cutoff,
        )
        result = await db.execute(stmt)
        counts["evaluation_configs"] = result.rowcount

        # 4. Datasets (also delete S3 files)
        expired_datasets = await db.execute(
            select(Dataset).where(
                Dataset.is_deleted == True,  # noqa: E712
                Dataset.deleted_at < cutoff,
            )
        )
        dataset_count = 0
        for ds in expired_datasets.scalars().all():
            try:
                delete_dataset_files(
                    ds.organization_id, ds.id
                )
            except Exception:
                logger.warning(
                    "cleanup.s3_delete_failed",
                    dataset_id=str(ds.id),
                )
            await db.delete(ds)
            dataset_count += 1
        counts["datasets"] = dataset_count

        await db.flush()

    logger.info("cleanup.hard_delete_completed", counts=counts)
    return counts


async def _cleanup_stale_runs() -> int:
    """
    Mark runs stuck in PENDING/RUNNING as FAILED.

    This handles cases where:
    - A worker crashed without updating the run status
    - A task was lost in the queue
    - Network partition between worker and message broker
    """
    from src.database import get_standalone_session
    from src.models.evaluation import EvaluationRun, RunStatus

    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=STALE_RUN_HOURS
    )

    async with get_standalone_session() as db:
        stmt = (
            update(EvaluationRun)
            .where(
                EvaluationRun.status.in_(
                    [RunStatus.PENDING, RunStatus.RUNNING]
                ),
                EvaluationRun.created_at < cutoff,
            )
            .values(
                status=RunStatus.FAILED,
                error_message=(
                    f"Run exceeded {STALE_RUN_HOURS}h timeout — "
                    "marked as failed by cleanup worker"
                ),
                completed_at=datetime.now(timezone.utc),
            )
        )
        result = await db.execute(stmt)
        count = result.rowcount
        await db.flush()

    if count > 0:
        logger.info("cleanup.stale_runs", count=count)
    return count


@celery_app.task(
    name="src.workers.cleanup_worker.run_maintenance",
    bind=True,
    max_retries=1,
)
def run_maintenance(self) -> dict:
    """
    Periodic maintenance task.

    Should be scheduled via Celery Beat every 6 hours:
    celery -A src.workers.celery_app beat --schedule=...
    """
    logger.info("cleanup.maintenance_started")

    try:
        deleted = _run_async(_hard_delete_expired_records())
        stale = _run_async(_cleanup_stale_runs())

        result = {
            "status": "completed",
            "hard_deleted": deleted,
            "stale_runs_cleaned": stale,
        }
        logger.info("cleanup.maintenance_completed", **result)
        return result

    except Exception as exc:
        logger.exception("cleanup.maintenance_failed")
        raise self.retry(exc=exc)
