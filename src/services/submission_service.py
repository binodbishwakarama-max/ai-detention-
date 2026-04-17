"""
Submission service — business logic for the submission lifecycle.

Handles CRUD for startup submissions and triggers evaluation runs
via the Celery orchestrator pipeline.

Lifecycle:
  DRAFT → SUBMITTED → UNDER_REVIEW → EVALUATED → ARCHIVED
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
from src.models.evaluation import EvaluationConfig, EvaluationRun, RunStatus
from src.models.organization import Organization
from src.models.submission import Submission, SubmissionStatus
from src.services.audit_service import create_audit_log

logger = structlog.get_logger(__name__)


# ── Submission CRUD ──────────────────────────────────────


async def create_submission(
    db: AsyncSession,
    *,
    org_id: UUID,
    user_id: UUID,
    startup_name: str,
    description: str | None = None,
    website_url: str | None = None,
    pitch_deck_url: str | None = None,
    metadata: dict | None = None,
    ip_address: str | None = None,
) -> Submission:
    """Create a new startup submission in DRAFT status."""
    submission = Submission(
        organization_id=org_id,
        submitted_by_id=user_id,
        startup_name=startup_name,
        description=description,
        website_url=website_url,
        pitch_deck_url=pitch_deck_url,
        status=SubmissionStatus.DRAFT,
        metadata_=metadata or {},
    )
    db.add(submission)
    await db.flush()

    await create_audit_log(
        db,
        action=AuditAction.CREATE,
        resource_type="submission",
        resource_id=str(submission.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )

    logger.info(
        "submission.created",
        submission_id=str(submission.id),
        startup_name=startup_name,
    )
    return submission


async def get_submission(
    db: AsyncSession,
    *,
    submission_id: UUID,
    org_id: UUID,
) -> Submission:
    """Fetch a submission by ID, scoped to an organization."""
    result = await db.execute(
        select(Submission).where(
            Submission.id == submission_id,
            Submission.organization_id == org_id,
            Submission.deleted_at.is_(None),  # noqa: E712
        )
    )
    submission = result.scalar_one_or_none()
    if not submission:
        raise NotFoundError("Submission", str(submission_id))
    return submission


async def list_submissions(
    db: AsyncSession,
    *,
    org_id: UUID,
    status_filter: SubmissionStatus | None = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[Submission], int]:
    """List submissions for an organization with pagination."""
    base_where = [
        Submission.organization_id == org_id,
        Submission.deleted_at.is_(None),  # noqa: E712
    ]
    if status_filter:
        base_where.append(Submission.status == status_filter)

    count_stmt = (
        select(func.count())
        .select_from(Submission)
        .where(*base_where)
    )
    total = (await db.execute(count_stmt)).scalar() or 0

    stmt = (
        select(Submission)
        .where(*base_where)
        .order_by(Submission.created_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(stmt)
    submissions = list(result.scalars().all())

    return submissions, total


async def update_submission(
    db: AsyncSession,
    *,
    submission_id: UUID,
    org_id: UUID,
    user_id: UUID,
    updates: dict,
    ip_address: str | None = None,
) -> Submission:
    """Update a submission's fields."""
    submission = await get_submission(db, submission_id=submission_id, org_id=org_id)

    for field, value in updates.items():
        if value is not None and hasattr(submission, field):
            setattr(submission, field, value)

    await db.flush()

    await create_audit_log(
        db,
        action=AuditAction.UPDATE,
        resource_type="submission",
        resource_id=str(submission.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )

    return submission


async def delete_submission(
    db: AsyncSession,
    *,
    submission_id: UUID,
    org_id: UUID,
    user_id: UUID,
    ip_address: str | None = None,
) -> None:
    """Soft-delete a submission."""
    submission = await get_submission(db, submission_id=submission_id, org_id=org_id)
    submission.soft_delete()
    await db.flush()

    await create_audit_log(
        db,
        action=AuditAction.DELETE,
        resource_type="submission",
        resource_id=str(submission.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )


# ── Trigger Evaluation ───────────────────────────────────


async def trigger_evaluation(
    db: AsyncSession,
    *,
    submission_id: UUID,
    org_id: UUID,
    user_id: UUID,
    config_id: UUID | None = None,
    run_metadata: dict | None = None,
    ip_address: str | None = None,
) -> EvaluationRun:
    """
    Trigger a new evaluation run on a submission.

    Dispatches the run to the Celery orchestrator pipeline.
    Validates concurrent evaluation limits per organization.
    """
    # Fetch and validate submission
    submission = await get_submission(db, submission_id=submission_id, org_id=org_id)

    if submission.status == SubmissionStatus.ARCHIVED:
        raise ConflictError("Cannot evaluate an archived submission")

    # Validate config if provided
    config_snapshot = {}
    if config_id:
        config_result = await db.execute(
            select(EvaluationConfig).where(
                EvaluationConfig.id == config_id,
                EvaluationConfig.organization_id == org_id,
                EvaluationConfig.deleted_at.is_(None),  # noqa: E712
            )
        )
        config = config_result.scalar_one_or_none()
        if not config:
            raise NotFoundError("Evaluation config", str(config_id))
        config_snapshot = config.pipeline_config

    # Check concurrent evaluation limit
    active_count_stmt = (
        select(func.count())
        .select_from(EvaluationRun)
        .where(
            EvaluationRun.organization_id == org_id,
            EvaluationRun.status.in_([
                RunStatus.PENDING,
                RunStatus.RUNNING,
            ]),
        )
    )
    active_count = (await db.execute(active_count_stmt)).scalar() or 0

    org_result = await db.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = org_result.scalar_one()

    if active_count >= org.max_concurrent_evaluations:
        raise ConflictError(
            f"Maximum concurrent evaluations ({org.max_concurrent_evaluations}) "
            "reached. Wait for existing runs to complete."
        )

    # Transition submission status
    if submission.status == SubmissionStatus.DRAFT:
        submission.status = SubmissionStatus.SUBMITTED
    if submission.status in (SubmissionStatus.SUBMITTED, SubmissionStatus.EVALUATED):
        submission.status = SubmissionStatus.UNDER_REVIEW

    # Create the evaluation run
    run = EvaluationRun(
        submission_id=submission_id,
        config_id=config_id,
        organization_id=org_id,
        triggered_by_id=user_id,
        status=RunStatus.PENDING,
        config_snapshot=config_snapshot,
        run_metadata=run_metadata or {},
    )
    db.add(run)
    await db.flush()

    # Dispatch to Celery orchestrator
    from src.workers.tasks.orchestrator import evaluate_submission

    task = evaluate_submission.delay(str(run.id))
    run.celery_task_id = task.id
    await db.flush()

    await create_audit_log(
        db,
        action=AuditAction.EVALUATION_STARTED,
        resource_type="evaluation_run",
        resource_id=str(run.id),
        organization_id=org_id,
        user_id=user_id,
        ip_address=ip_address,
    )

    logger.info(
        "submission.evaluation_triggered",
        run_id=str(run.id),
        submission_id=str(submission_id),
        celery_task_id=task.id,
    )
    return run
