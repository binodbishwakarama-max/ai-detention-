"""
Orchestrator — the entry point that triggers the evaluation pipeline.

Uses Celery's chord primitive:
1. Fan-out: 4 analysis tasks run in parallel
2. Callback: when ALL 4 complete, cross_check runs
3. Chain: cross_check → fabrication → llm_judge → finalize

Chord guarantees:
- All parallel tasks must complete (or fail) before callback fires
- If any parallel task fails, the chord error callback fires
- The chord result aggregates all parallel task outputs
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from uuid import UUID

import structlog
from celery import chain, chord, group

from src.workers.celery_app import celery_app
from src.workers.tasks.base_task import _run_async

logger = structlog.get_logger(__name__)


async def _prepare_run(run_id: str) -> dict:
    """
    Prepare the evaluation run for processing.

    Transitions the run to RUNNING status and returns
    the submission data needed by workers.
    """
    from sqlalchemy import select
    from src.database import get_standalone_session
    from src.models.evaluation import EvaluationRun, RunStatus
    from src.models.submission import Submission
    from src.repositories.evaluation_run_repository import evaluation_run_repo

    async with get_standalone_session() as db:
        # Get the run
        result = await db.execute(
            select(EvaluationRun).where(EvaluationRun.id == UUID(run_id))
        )
        run = result.scalar_one_or_none()
        if not run:
            raise ValueError(f"Evaluation run {run_id} not found")

        if run.is_terminal:
            logger.info("orchestrator.run_already_terminal", run_id=run_id)
            return {}

        # Transition to RUNNING with optimistic lock
        await evaluation_run_repo.transition_status(
            db,
            run_id=UUID(run_id),
            expected_version=run.version,
            new_status=RunStatus.RUNNING,
            total_workers=4,
        )

        # Get submission data
        sub_result = await db.execute(
            select(Submission).where(Submission.id == run.submission_id)
        )
        submission = sub_result.scalar_one()

        return {
            "run_id": run_id,
            "org_id": str(run.organization_id),
            "submission_id": str(submission.id),
            "startup_name": submission.startup_name,
            "website_url": submission.website_url,
            "pitch_deck_url": submission.pitch_deck_url,
            "raw_content": submission.raw_content,
            "metadata": submission.metadata_,
            "config_snapshot": run.config_snapshot,
        }


@celery_app.task(
    name="src.workers.tasks.orchestrator.evaluate_submission",
    bind=True,
    max_retries=1,
    soft_time_limit=600,
    time_limit=660,
    acks_late=True,
)
def evaluate_submission(self, run_id: str) -> dict:
    """
    Orchestrate the full evaluation pipeline for a submission.

    Pipeline:
    1. [PARALLEL] github + pitch_deck + video + web_verification
    2. [SEQUENTIAL] cross_check → fabrication → llm_judge → finalize

    Uses chord() for the parallel fan-out, then chain() for sequential.
    """
    task_id = self.request.id
    logger.info(
        "orchestrator.started",
        run_id=run_id,
        task_id=task_id,
    )

    try:
        # Prepare the run (transition to RUNNING, load submission data)
        context = _run_async(_prepare_run(run_id))
        if not context:
            return {"status": "skipped", "reason": "run already terminal"}

        # Import task signatures
        from src.workers.tasks.github_analysis import github_analysis_task
        from src.workers.tasks.pitch_deck import pitch_deck_task
        from src.workers.tasks.video_analysis import video_analysis_task
        from src.workers.tasks.web_verification import web_verification_task
        from src.workers.tasks.cross_check import cross_check_task
        from src.workers.tasks.fabrication import fabrication_detection_task
        from src.workers.tasks.llm_judge import llm_judge_task
        from src.workers.tasks.finalize import finalize_and_notify_task

        # ── Stage 1: Parallel analysis (chord) ───────────
        parallel_tasks = group(
            github_analysis_task.s(run_id, **context),
            pitch_deck_task.s(run_id, **context),
            video_analysis_task.s(run_id, **context),
            web_verification_task.s(run_id, **context),
        )

        # ── Stage 2: Sequential processing (chain) ───────
        # The chord callback receives the list of parallel results
        sequential_pipeline = chain(
            cross_check_task.s(run_id),
            fabrication_detection_task.s(run_id),
            llm_judge_task.s(run_id),
            finalize_and_notify_task.s(run_id),
        )

        # ── Execute: chord (parallel) → chain (sequential)
        pipeline = chord(parallel_tasks)(sequential_pipeline)

        logger.info(
            "orchestrator.pipeline_dispatched",
            run_id=run_id,
            parallel_tasks=4,
            sequential_tasks=4,
        )

        return {
            "status": "dispatched",
            "run_id": run_id,
            "pipeline_id": str(pipeline.id),
        }

    except Exception as exc:
        logger.exception("orchestrator.failed", run_id=run_id)
        # Mark run as failed
        _run_async(_fail_run(run_id, str(exc)))
        raise self.retry(exc=exc)


async def _fail_run(run_id: str, error: str) -> None:
    """Mark a run as failed in the database."""
    from src.database import get_standalone_session
    from src.repositories.evaluation_run_repository import evaluation_run_repo
    from src.models.evaluation import EvaluationRun, RunStatus
    from sqlalchemy import select

    try:
        async with get_standalone_session() as db:
            result = await db.execute(
                select(EvaluationRun).where(
                    EvaluationRun.id == UUID(run_id)
                )
            )
            run = result.scalar_one_or_none()
            if run and not run.is_terminal:
                await evaluation_run_repo.transition_status(
                    db, UUID(run_id), run.version,
                    RunStatus.FAILED, error_message=error,
                )
    except Exception:
        logger.exception("orchestrator.fail_run_error")
