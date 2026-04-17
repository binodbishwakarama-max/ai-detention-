"""
Submission endpoints — CRUD and evaluation trigger for startup submissions.

Routes:
  POST   /submissions              — Create a submission
  GET    /submissions              — List submissions (paginated)
  GET    /submissions/{id}         — Get submission detail
  PATCH  /submissions/{id}         — Update a submission
  DELETE /submissions/{id}         — Soft-delete a submission
  POST   /submissions/{id}/evaluate — Trigger evaluation pipeline
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Request, status

from src.api.deps import (
    CurrentUser,
    DbSession,
    Pagination,
    RequireMember,
    get_client_ip,
)
from src.schemas.common import MessageResponse
from src.schemas.evaluation import EvaluationRunResponse
from src.schemas.submission import (
    SubmissionCreate,
    SubmissionEvaluate,
    SubmissionResponse,
    SubmissionUpdate,
)
from src.services import submission_service
from src.utils.pagination import build_paginated_response

router = APIRouter(prefix="/submissions", tags=["Submissions"])


@router.post(
    "",
    response_model=SubmissionResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new startup submission",
    dependencies=[RequireMember],
)
async def create_submission(
    request: Request,
    body: SubmissionCreate,
    user: CurrentUser,
    db: DbSession,
) -> SubmissionResponse:
    """Create a new startup submission in DRAFT status."""
    ip = get_client_ip(request)
    submission = await submission_service.create_submission(
        db,
        org_id=user.organization_id,
        user_id=user.id,
        startup_name=body.startup_name,
        description=body.description,
        website_url=body.website_url,
        pitch_deck_url=body.pitch_deck_url,
        metadata=body.metadata,
        ip_address=ip,
    )
    return SubmissionResponse.model_validate(submission)


@router.get(
    "",
    summary="List submissions",
)
async def list_submissions(
    user: CurrentUser,
    db: DbSession,
    pagination: Pagination,
    status_filter: str | None = None,
) -> dict:
    """List submissions for the authenticated user's organization."""
    from src.models.submission import SubmissionStatus

    parsed_status = None
    if status_filter:
        try:
            parsed_status = SubmissionStatus(status_filter)
        except ValueError:
            pass

    submissions, total = await submission_service.list_submissions(
        db,
        org_id=user.organization_id,
        status_filter=parsed_status,
        page=pagination.page,
        page_size=pagination.page_size,
    )
    items = [SubmissionResponse.model_validate(s) for s in submissions]
    return build_paginated_response(items, total, pagination)


@router.get(
    "/{submission_id}",
    response_model=SubmissionResponse,
    summary="Get submission detail",
)
async def get_submission(
    submission_id: UUID,
    user: CurrentUser,
    db: DbSession,
) -> SubmissionResponse:
    """Fetch a specific submission by ID."""
    submission = await submission_service.get_submission(
        db, submission_id=submission_id, org_id=user.organization_id
    )
    return SubmissionResponse.model_validate(submission)


@router.patch(
    "/{submission_id}",
    response_model=SubmissionResponse,
    summary="Update a submission",
    dependencies=[RequireMember],
)
async def update_submission(
    submission_id: UUID,
    request: Request,
    body: SubmissionUpdate,
    user: CurrentUser,
    db: DbSession,
) -> SubmissionResponse:
    """Update submission fields. Only non-null fields are applied."""
    ip = get_client_ip(request)
    updates = body.model_dump(exclude_unset=True)

    submission = await submission_service.update_submission(
        db,
        submission_id=submission_id,
        org_id=user.organization_id,
        user_id=user.id,
        updates=updates,
        ip_address=ip,
    )
    return SubmissionResponse.model_validate(submission)


@router.delete(
    "/{submission_id}",
    response_model=MessageResponse,
    summary="Delete a submission",
    dependencies=[RequireMember],
)
async def delete_submission(
    submission_id: UUID,
    request: Request,
    user: CurrentUser,
    db: DbSession,
) -> MessageResponse:
    """Soft-delete a submission."""
    ip = get_client_ip(request)
    await submission_service.delete_submission(
        db,
        submission_id=submission_id,
        org_id=user.organization_id,
        user_id=user.id,
        ip_address=ip,
    )
    return MessageResponse(message="Submission deleted successfully")


@router.post(
    "/{submission_id}/evaluate",
    response_model=EvaluationRunResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Trigger evaluation on a submission",
    dependencies=[RequireMember],
)
async def trigger_evaluation(
    submission_id: UUID,
    request: Request,
    body: SubmissionEvaluate,
    user: CurrentUser,
    db: DbSession,
) -> EvaluationRunResponse:
    """
    Trigger a new evaluation run on a submission.

    Dispatches the pipeline to Celery workers. Returns the created
    EvaluationRun with a celery_task_id for tracking.
    """
    ip = get_client_ip(request)
    run = await submission_service.trigger_evaluation(
        db,
        submission_id=submission_id,
        org_id=user.organization_id,
        user_id=user.id,
        config_id=body.config_id,
        run_metadata=body.metadata,
        ip_address=ip,
    )
    return EvaluationRunResponse.model_validate(run)
