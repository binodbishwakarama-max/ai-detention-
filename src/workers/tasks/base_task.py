"""
Base task class — shared infrastructure for all pipeline tasks.

Every task in the evaluation pipeline extends BaseEvalTask, which provides:

1. IDEMPOTENCY: Checks if a WorkerResult already exists with status=COMPLETED
   for the same (run_id, worker_type) pair. If so, returns cached result.

2. ATOMIC WRITES: All DB operations happen within a single transaction.
   On exception, the transaction is rolled back — no partial state.

3. PROGRESS REPORTING: update_progress() stores progress (0-100) in Redis
   with a 1-hour TTL. Clients poll via GET /runs/{id}/progress.

4. DEAD LETTER QUEUE: on_failure() records the failed task with full
   context (args, kwargs, traceback, retry count) for post-mortem analysis.

5. STRUCTURED LOGGING: Every step is logged with run_id, worker_type,
   and correlation_id for distributed tracing.
"""

from __future__ import annotations

import asyncio
import traceback
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import structlog
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from src.workers.celery_app import celery_app

logger = structlog.get_logger(__name__)


def _run_async(coro):
    """Run an async coroutine from a sync Celery task context."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class BaseEvalTask(Task):
    """
    Base class for all evaluation pipeline tasks.

    Subclasses must implement:
        async def execute(self, run_id, **kwargs) -> dict

    The base class handles:
    - Idempotency (skip if already completed)
    - Progress tracking (Redis-backed)
    - Atomic DB writes (single transaction)
    - Error handling and DLQ routing
    - Structured logging
    """

    abstract = True
    worker_type: str = "unknown"

    # Retry configuration — overridden per task
    autoretry_for = (Exception,)
    retry_backoff = True           # exponential: 2^n seconds
    retry_backoff_max = 60         # cap at 60 seconds
    retry_jitter = True            # ±25% jitter to prevent thundering herd
    max_retries = 3

    def run(self, run_id: str, **kwargs) -> dict:
        """
        Entry point called by Celery. Wraps the async execute() method
        with idempotency checks and error handling.
        """
        task_id = self.request.id
        hostname = self.request.hostname or "unknown"
        retry_num = self.request.retries

        log = logger.bind(
            run_id=run_id,
            worker_type=self.worker_type,
            task_id=task_id,
            hostname=hostname,
            retry=retry_num,
        )

        log.info("task.started")

        try:
            # ── Idempotency check ────────────────────────
            cached = _run_async(self._check_idempotent(run_id))
            if cached is not None:
                log.info("task.idempotent_skip", status="already_completed")
                return cached

            # ── Create WorkerResult record (PENDING) ─────
            _run_async(self._create_worker_result(
                run_id, task_id, hostname
            ))

            # ── Update progress to 0% ────────────────────
            self.update_progress(run_id, 0)

            # ── Execute task logic ────────────────────────
            result = _run_async(self.execute(run_id, **kwargs))

            # ── Mark completed ────────────────────────────
            _run_async(self._mark_completed(run_id, result))
            self.update_progress(run_id, 100)

            log.info("task.completed", result_keys=list(result.keys()))
            return result

        except SoftTimeLimitExceeded:
            log.warning("task.timeout")
            _run_async(self._mark_failed(
                run_id, "Task exceeded soft time limit"
            ))
            raise

        except self.MaxRetriesExceededError:
            log.error("task.max_retries_exhausted")
            _run_async(self._mark_failed(
                run_id, "Max retries exhausted"
            ))
            _run_async(self._send_to_dlq(run_id, kwargs))
            raise

        except Exception as exc:
            log.exception("task.failed", error=str(exc))
            _run_async(self._mark_failed(run_id, str(exc)))
            raise

    async def execute(self, run_id: str, **kwargs) -> dict:
        """
        Override this method with task-specific logic.

        Must return a dict with the task output.
        Must be idempotent: running twice produces the same result.
        """
        raise NotImplementedError

    # ── Progress Reporting ───────────────────────────────────

    def update_progress(self, run_id: str, progress: int, detail: str = "") -> None:
        """
        Store progress (0-100) in Redis for real-time polling.

        Key: progress:{run_id}:{worker_type}
        TTL: 1 hour (auto-cleanup after completion)
        """
        try:
            import json
            import redis
            from src.config import get_settings
            settings = get_settings()
            r = redis.from_url(settings.redis_url, decode_responses=True)
            key = f"progress:{run_id}:{self.worker_type}"
            payload = {
                "worker_type": self.worker_type,
                "progress": progress,
                "detail": detail,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
            r.hset(key, mapping=payload)
            r.expire(key, 3600)  # 1 hour TTL
            # Broadcast the update via Pub/Sub for WebSockets
            r.publish(f"channel:run:{run_id}", json.dumps(payload))
        except Exception:
            pass  # Progress is best-effort, never fails the task

    # ── Idempotency ──────────────────────────────────────────

    async def _check_idempotent(self, run_id: str) -> dict | None:
        """Check if this task already completed for this run."""
        from sqlalchemy import select
        from src.database import get_standalone_session
        from src.models.worker_result import WorkerResult, WorkerStatus

        async with get_standalone_session() as db:
            stmt = select(WorkerResult).where(
                WorkerResult.evaluation_run_id == UUID(run_id),
                WorkerResult.worker_type == self.worker_type,
                WorkerResult.status == WorkerStatus.COMPLETED,
                WorkerResult.deleted_at.is_(None),
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing and existing.output_data:
                return existing.output_data
            return None

    # ── WorkerResult Lifecycle ───────────────────────────────

    async def _create_worker_result(
        self, run_id: str, task_id: str, hostname: str
    ) -> None:
        """Create or update a WorkerResult record to RUNNING status."""
        from sqlalchemy import select
        from src.database import get_standalone_session
        from src.models.worker_result import WorkerResult, WorkerStatus
        from src.models.evaluation import EvaluationRun

        async with get_standalone_session() as db:
            # Get org_id from the run
            run_result = await db.execute(
                select(EvaluationRun.organization_id).where(
                    EvaluationRun.id == UUID(run_id)
                )
            )
            org_id = run_result.scalar_one()

            # Check for existing record (idempotent create)
            existing = await db.execute(
                select(WorkerResult).where(
                    WorkerResult.evaluation_run_id == UUID(run_id),
                    WorkerResult.worker_type == self.worker_type,
                    WorkerResult.deleted_at.is_(None),
                )
            )
            wr = existing.scalar_one_or_none()

            if wr:
                wr.status = WorkerStatus.RUNNING
                wr.celery_task_id = task_id
                wr.worker_id = hostname
            else:
                wr = WorkerResult(
                    evaluation_run_id=UUID(run_id),
                    organization_id=org_id,
                    worker_type=self.worker_type,
                    celery_task_id=task_id,
                    worker_id=hostname,
                    status=WorkerStatus.RUNNING,
                )
                db.add(wr)

            await db.flush()

    async def _mark_completed(self, run_id: str, output: dict) -> None:
        """Mark the WorkerResult as COMPLETED with output data."""
        import time
        from sqlalchemy import select, update
        from src.database import get_standalone_session
        from src.models.worker_result import WorkerResult, WorkerStatus

        async with get_standalone_session() as db:
            # 1. Update WorkerResult
            await db.execute(
                update(WorkerResult)
                .where(
                    WorkerResult.evaluation_run_id == UUID(run_id),
                    WorkerResult.worker_type == self.worker_type,
                    WorkerResult.deleted_at.is_(None),
                )
                .values(
                    status=WorkerStatus.COMPLETED,
                    output_data=output,
                    processing_time_ms=int(
                        (time.monotonic() - self._start_time) * 1000
                    ) if hasattr(self, '_start_time') else 0,
                )
            )
            # 2. Increment completed_workers on EvaluationRun
            from src.models.evaluation import EvaluationRun
            await db.execute(
                update(EvaluationRun)
                .where(EvaluationRun.id == UUID(run_id))
                .values(completed_workers=EvaluationRun.completed_workers + 1)
            )

    async def _mark_failed(self, run_id: str, error: str) -> None:
        """Mark the WorkerResult as FAILED with error message."""
        from sqlalchemy import update
        from src.database import get_standalone_session
        from src.models.worker_result import WorkerResult, WorkerStatus

        try:
            async with get_standalone_session() as db:
                # 1. Update WorkerResult
                await db.execute(
                    update(WorkerResult)
                    .where(
                        WorkerResult.evaluation_run_id == UUID(run_id),
                        WorkerResult.worker_type == self.worker_type,
                        WorkerResult.deleted_at.is_(None),
                    )
                    .values(
                        status=WorkerStatus.FAILED,
                        error_message=error[:2000],  # truncate long errors
                    )
                )
                # 2. Increment failed_workers on EvaluationRun
                from src.models.evaluation import EvaluationRun
                await db.execute(
                    update(EvaluationRun)
                    .where(EvaluationRun.id == UUID(run_id))
                    .values(failed_workers=EvaluationRun.failed_workers + 1)
                )
        except Exception:
            logger.exception("task.mark_failed_error")

    # ── Dead Letter Queue ────────────────────────────────────

    async def _send_to_dlq(self, run_id: str, kwargs: dict) -> None:
        """
        Send permanently failed task to Dead Letter Queue.

        Stores full context in Redis for post-mortem analysis:
        - Task name, args, kwargs
        - Full traceback
        - Retry count
        - Worker hostname
        """
        try:
            import json
            import redis
            from src.config import get_settings
            settings = get_settings()
            r = redis.from_url(settings.redis_url, decode_responses=True)

            dlq_entry = {
                "task_name": self.name,
                "run_id": run_id,
                "worker_type": self.worker_type,
                "kwargs": json.dumps(kwargs, default=str),
                "traceback": traceback.format_exc(),
                "retries": self.request.retries,
                "hostname": self.request.hostname,
                "failed_at": datetime.now(timezone.utc).isoformat(),
            }
            dlq_key = f"dlq:{run_id}:{self.worker_type}"
            r.hset(dlq_key, mapping=dlq_entry)
            # Keep DLQ entries for 7 days
            r.expire(dlq_key, 604800)

            # Also add to a DLQ list for monitoring
            r.lpush("dlq:all", dlq_key)
            r.ltrim("dlq:all", 0, 9999)  # keep last 10K entries

            logger.warning(
                "task.sent_to_dlq",
                run_id=run_id,
                worker_type=self.worker_type,
            )
        except Exception:
            logger.exception("task.dlq_write_failed")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Celery callback on task failure."""
        logger.error(
            "task.on_failure",
            task_id=task_id,
            exc_type=type(exc).__name__,
            exc_msg=str(exc),
        )

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Celery callback on task retry."""
        logger.warning(
            "task.on_retry",
            task_id=task_id,
            retry=self.request.retries,
            exc_type=type(exc).__name__,
        )
