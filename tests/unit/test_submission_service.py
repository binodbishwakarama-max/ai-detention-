import pytest
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from src.services import submission_service
from src.models.submission import SubmissionStatus
from src.middleware.error_handler import NotFoundError, ConflictError
from tests.factories import create_organization, create_user, create_submission, create_evaluation_config

@pytest.mark.asyncio
async def test_create_submission(db_session: AsyncSession, test_org, test_user):
    submission = await submission_service.create_submission(
        db_session,
        org_id=test_org.id,
        user_id=test_user.id,
        startup_name="Acme AI",
        description="AI for everyone",
        website_url="https://acme.ai"
    )
    
    assert submission.startup_name == "Acme AI"
    assert submission.status == SubmissionStatus.DRAFT
    assert submission.organization_id == test_org.id

@pytest.mark.asyncio
async def test_get_submission(db_session: AsyncSession, test_org, test_user):
    created = await create_submission(db_session, organization=test_org, user=test_user)
    
    fetched = await submission_service.get_submission(
        db_session, submission_id=created.id, org_id=test_org.id
    )
    
    assert fetched.id == created.id
    assert fetched.startup_name == created.startup_name

@pytest.mark.asyncio
async def test_get_submission_not_found(db_session: AsyncSession, test_org):
    with pytest.raises(NotFoundError):
        await submission_service.get_submission(
            db_session, submission_id=uuid4(), org_id=test_org.id
        )

@pytest.mark.asyncio
async def test_list_submissions(db_session: AsyncSession, test_org, test_user):
    await create_submission(db_session, organization=test_org, user=test_user)
    await create_submission(db_session, organization=test_org, user=test_user)
    
    submissions, total = await submission_service.list_submissions(
        db_session, org_id=test_org.id
    )
    
    assert total == 2
    assert len(submissions) == 2

@pytest.mark.asyncio
async def test_update_submission(db_session: AsyncSession, test_org, test_user):
    submission = await create_submission(db_session, organization=test_org, user=test_user)
    
    updated = await submission_service.update_submission(
        db_session,
        submission_id=submission.id,
        org_id=test_org.id,
        user_id=test_user.id,
        updates={"startup_name": "New Name"}
    )
    
    assert updated.startup_name == "New Name"

@pytest.mark.asyncio
async def test_delete_submission(db_session: AsyncSession, test_org, test_user):
    submission = await create_submission(db_session, organization=test_org, user=test_user)
    
    await submission_service.delete_submission(
        db_session, submission_id=submission.id, org_id=test_org.id, user_id=test_user.id
    )
    
    with pytest.raises(NotFoundError):
        await submission_service.get_submission(
            db_session, submission_id=submission.id, org_id=test_org.id
        )

@pytest.mark.asyncio
async def test_trigger_evaluation(db_session: AsyncSession, test_org, test_user, test_config, mock_celery):
    submission = await create_submission(db_session, organization=test_org, user=test_user)
    
    run = await submission_service.trigger_evaluation(
        db_session,
        submission_id=submission.id,
        org_id=test_org.id,
        user_id=test_user.id,
        config_id=test_config.id
    )
    
    assert run.submission_id == submission.id
    assert run.config_id == test_config.id
    assert submission.status == SubmissionStatus.UNDER_REVIEW
    mock_celery.assert_called_once()

@pytest.mark.asyncio
async def test_trigger_evaluation_concurrent_limit(db_session: AsyncSession, test_org, test_user, test_config):
    # Set limit to 0 for testing
    test_org.max_concurrent_evaluations = 0
    await db_session.flush()
    
    submission = await create_submission(db_session, organization=test_org, user=test_user)
    
    with pytest.raises(ConflictError, match="Maximum concurrent evaluations"):
        await submission_service.trigger_evaluation(
            db_session,
            submission_id=submission.id,
            org_id=test_org.id,
            user_id=test_user.id,
            config_id=test_config.id
        )
