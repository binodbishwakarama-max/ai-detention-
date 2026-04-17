"""
Export worker — handles asynchronous result export to S3.

For large evaluation runs (100K+ results), exporting synchronously
would timeout the API request. This worker handles exports in the
background and can optionally notify via webhook when complete.
"""

from __future__ import annotations

import asyncio

import structlog

from src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from sync Celery context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _execute_export(
    run_id: str, org_id: str, fmt: str
) -> dict:
    """Execute the export operation."""
    from uuid import UUID

    from src.database import get_standalone_session
    from src.services.result_service import export_results

    async with get_standalone_session() as db:
        download_url = await export_results(
            db,
            run_id=UUID(run_id),
            org_id=UUID(org_id),
            fmt=fmt,
        )
        return {
            "status": "completed",
            "download_url": download_url,
        }


@celery_app.task(
    name="src.workers.export_worker.export_evaluation_results",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    acks_late=True,
)
def export_evaluation_results(
    self, run_id: str, org_id: str, fmt: str = "json"
) -> dict:
    """
    Export evaluation results to S3 in the requested format.

    Supports: json, csv, parquet
    """
    logger.info(
        "export.started",
        run_id=run_id,
        format=fmt,
        task_id=self.request.id,
    )

    try:
        result = _run_async(
            _execute_export(run_id, org_id, fmt)
        )
        logger.info(
            "export.completed",
            run_id=run_id,
            format=fmt,
        )
        return result
    except Exception as exc:
        logger.exception(
            "export.failed",
            run_id=run_id,
            error=str(exc),
        )
        raise self.retry(exc=exc)
