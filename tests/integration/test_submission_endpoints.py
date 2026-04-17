import pytest
from uuid import uuid4
from httpx import AsyncClient
from src.models.submission import SubmissionStatus
from tests.factories import create_submission, create_evaluation_config

@pytest.mark.asyncio
async def test_create_submission_api(client: AsyncClient, auth_headers: dict):
    payload = {
        "startup_name": "API Startup",
        "description": "Created via API",
        "website_url": "https://api.test"
    }
    response = await client.post("/api/v1/submissions", json=payload, headers=auth_headers)
    
    assert response.status_code == 201
    data = response.json()
    assert data["startup_name"] == "API Startup"
    assert data["status"] == "draft"

@pytest.mark.asyncio
async def test_list_submissions_api(client: AsyncClient, auth_headers: dict, db_session, test_org, test_user):
    await create_submission(db_session, organization=test_org, user=test_user)
    
    response = await client.get("/api/v1/submissions", headers=auth_headers)
    
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 1
    assert len(data["items"]) >= 1

@pytest.mark.asyncio
async def test_get_submission_api(client: AsyncClient, auth_headers: dict, db_session, test_org, test_user):
    submission = await create_submission(db_session, organization=test_org, user=test_user)
    
    response = await client.get(f"/api/v1/submissions/{submission.id}", headers=auth_headers)
    
    assert response.status_code == 200
    assert response.json()["id"] == str(submission.id)

@pytest.mark.asyncio
async def test_update_submission_api(client: AsyncClient, auth_headers: dict, db_session, test_org, test_user):
    submission = await create_submission(db_session, organization=test_org, user=test_user)
    
    payload = {"startup_name": "Updated by API"}
    response = await client.patch(f"/api/v1/submissions/{submission.id}", json=payload, headers=auth_headers)
    
    assert response.status_code == 200
    assert response.json()["startup_name"] == "Updated by API"

@pytest.mark.asyncio
async def test_delete_submission_api(client: AsyncClient, auth_headers: dict, db_session, test_org, test_user):
    submission = await create_submission(db_session, organization=test_org, user=test_user)
    
    response = await client.delete(f"/api/v1/submissions/{submission.id}", headers=auth_headers)
    
    assert response.status_code == 200
    
    # Verify it's gone
    get_res = await client.get(f"/api/v1/submissions/{submission.id}", headers=auth_headers)
    assert get_res.status_code == 404

@pytest.mark.asyncio
async def test_trigger_evaluation_api(client: AsyncClient, auth_headers: dict, db_session, test_org, test_user, test_config, mock_celery):
    submission = await create_submission(db_session, organization=test_org, user=test_user)
    
    payload = {"config_id": str(test_config.id)}
    response = await client.post(f"/api/v1/submissions/{submission.id}/evaluate", json=payload, headers=auth_headers)
    
    assert response.status_code == 202
    data = response.json()
    assert data["submission_id"] == str(submission.id)
    assert data["status"] == "pending"
    mock_celery.assert_called_once()
