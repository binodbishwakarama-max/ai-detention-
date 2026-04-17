"""
Finalize & Notify Task — computes final score and sends notifications.

Final step in the pipeline:
1. Computes weighted aggregate score across all dimensions
2. Applies contradiction penalty
3. Updates the evaluation run with final results
4. Sends webhook notification
5. Generates audit log entry
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from uuid import UUID

import structlog

from src.workers.celery_app import celery_app
from src.workers.tasks.base_task import BaseEvalTask, _run_async

logger = structlog.get_logger(__name__)


async def _finalize(
    run_id: str,
    llm_result: dict,
    update_progress,
) -> dict:
    """
    Finalize the evaluation run.

    1. Compute weighted overall_score from Score records
    2. Apply contradiction penalty
    3. Transition run to COMPLETED
    4. Send webhook notification
    5. Log audit entry
    """
    from sqlalchemy import select
    from src.database import get_standalone_session
    from src.models.evaluation import EvaluationRun, RunStatus
    from src.repositories.evaluation_run_repository import evaluation_run_repo
    from src.repositories.score_repository import score_repo
    from src.repositories.contradiction_repository import contradiction_repo
    from src.repositories.worker_result_repository import worker_result_repo
    from src.repositories.audit_log_repository import audit_log_repo
    from src.models.audit_log import AuditAction

    update_progress(run_id, 10, "Computing final weighted score")

    # ── Step 1: Compute weighted score ───────────────────
    async with get_standalone_session() as db:
        run_result = await db.execute(
            select(EvaluationRun).where(EvaluationRun.id == UUID(run_id))
        )
        run = run_result.scalar_one()

        if run.is_terminal:
            return {"status": "skipped", "reason": "Run already finalized"}

        # Get weighted average from score repository
        weighted_avg = await score_repo.compute_weighted_average(
            db, UUID(run_id), run.organization_id
        )

        # Get contradiction stats
        contradiction_buckets = await contradiction_repo.count_by_severity_bucket(
            db, UUID(run_id), run.organization_id
        )

    update_progress(run_id, 30, "Applying contradiction penalty")

    # ── Step 2: Apply contradiction penalty ──────────────
    critical_count = contradiction_buckets.get("critical", 0)
    high_count = contradiction_buckets.get("high", 0)
    medium_count = contradiction_buckets.get("medium", 0)

    penalty = (
        critical_count * 0.05   # -5% per critical contradiction
        + high_count * 0.03     # -3% per high
        + medium_count * 0.01   # -1% per medium
    )

    base_score = weighted_avg if weighted_avg is not None else 0.5
    final_score = max(0.0, min(1.0, round(base_score - penalty, 4)))

    update_progress(run_id, 50, "Counting worker results")

    # ── Step 3: Count worker statistics ──────────────────
    async with get_standalone_session() as db:
        worker_stats = await worker_result_repo.count_by_status(db, UUID(run_id))

    completed_workers = worker_stats.get("completed", 0)
    failed_workers = worker_stats.get("failed", 0)

    update_progress(run_id, 60, "Updating evaluation run")

    # ── Step 4: Transition run to COMPLETED ──────────────
    async with get_standalone_session() as db:
        # Re-fetch run for current version
        run_result = await db.execute(
            select(EvaluationRun).where(EvaluationRun.id == UUID(run_id))
        )
        run = run_result.scalar_one()

        if run.is_terminal:
            return {"status": "skipped", "reason": "Run already finalized"}

        await evaluation_run_repo.transition_status(
            db,
            run_id=UUID(run_id),
            expected_version=run.version,
            new_status=RunStatus.COMPLETED,
            overall_score=final_score,
            completed_workers=completed_workers,
            failed_workers=failed_workers,
        )

    update_progress(run_id, 75, "Logging audit trail")

    # ── Step 5: Audit log ────────────────────────────────
    async with get_standalone_session() as db:
        await audit_log_repo.create(
            db,
            action=AuditAction.EVALUATION_COMPLETED,
            resource_type="evaluation_run",
            resource_id=run_id,
            organization_id=run.organization_id,
            changes={
                "final_score": final_score,
                "base_score": base_score,
                "penalty": penalty,
                "contradiction_buckets": contradiction_buckets,
                "worker_stats": worker_stats,
                "llm_model_used": llm_result.get("model_used", "unknown"),
                "llm_cost_usd": llm_result.get("estimated_cost_usd", 0),
            },
        )

    update_progress(run_id, 85, "Sending webhook notification")

    # ── Step 6: Send webhook notification ────────────────
    try:
        from src.services.webhook_service import deliver_webhook
        config = run.config_snapshot or {}
        webhook_url = config.get("webhook_url")

        if webhook_url:
            await deliver_webhook(
                url=webhook_url,
                event_type="evaluation.completed",
                payload={
                    "run_id": run_id,
                    "submission_id": str(run.submission_id),
                    "status": "completed",
                    "final_score": final_score,
                    "scores": llm_result.get("scores", {}),
                    "key_strengths": llm_result.get("key_strengths", []),
                    "key_risks": llm_result.get("key_risks", []),
                    "contradictions": contradiction_buckets,
                },
                org_id=run.organization_id,
            )
    except Exception as e:
        logger.warning("finalize.webhook_failed", error=str(e))

    update_progress(run_id, 95, "Updating submission status")

    # ── Step 7: Update submission status ─────────────────
    try:
        from sqlalchemy import update
        from src.models.submission import Submission, SubmissionStatus

        async with get_standalone_session() as db:
            await db.execute(
                update(Submission)
                .where(Submission.id == run.submission_id)
                .values(status=SubmissionStatus.EVALUATED)
            )
    except Exception as e:
        logger.warning("finalize.submission_update_failed", error=str(e))

    # ── Step 8: Trigger L3 Materialized View Refresh ─────
    try:
        refresh_org_stats_task.delay()
    except Exception as e:
        logger.warning("finalize.mview_refresh_trigger_failed", error=str(e))

    result = {
        "status": "completed",
        "run_id": run_id,
        "final_score": final_score,
        "base_score": base_score,
        "contradiction_penalty": penalty,
        "completed_workers": completed_workers,
        "failed_workers": failed_workers,
    }

    logger.info(
        "finalize.evaluation_complete",
        run_id=run_id,
        final_score=final_score,
    )

    return result


@celery_app.task(
    name="src.workers.tasks.finalize.finalize_and_notify_task",
    base=BaseEvalTask,
    bind=True,
    max_retries=2,
    soft_time_limit=60,
    time_limit=90,
)
def finalize_and_notify_task(self, llm_result: dict, run_id: str, **kwargs) -> dict:
    """Finalize and notify task entry point."""
    self.worker_type = "finalize"
    self._start_time = time.monotonic()
    return _run_async(
        _finalize(run_id, llm_result, self.update_progress)
    )

@celery_app.task(
    name="src.workers.tasks.finalize.refresh_org_stats_task",
    bind=True,
    max_retries=2,
    soft_time_limit=120,
    time_limit=150,
)
def refresh_org_stats_task(self) -> dict:
    """Async scheduler to hydrate L3 caching Materialized Views."""
    import asyncio
    from sqlalchemy import text
    from src.database import get_standalone_session

    async def _do_refresh():
        async with get_standalone_session() as db:
            await db.execute(text("SELECT refresh_org_dashboard_stats();"))

    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(_do_refresh())
        else:
            loop.run_until_complete(_do_refresh())
    except RuntimeError:
        asyncio.run(_do_refresh())

    return {"status": "success", "task": "refresh_org_dashboard_stats"}
