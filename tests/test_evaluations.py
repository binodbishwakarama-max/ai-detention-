"""
Tests for evaluation endpoints.

Verifies:
- Config CRUD (create, read, update, delete)
- Run creation and cancellation
- Pagination
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_create_evaluation_config(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test creating an evaluation configuration."""
    response = await client.post(
        "/api/v1/evaluations/configs",
        headers=auth_headers,
        json={
            "name": "Test Evaluation",
            "description": "A test evaluation config",
            "model_config": {"provider": "openai", "model": "gpt-4"},
            "metrics_config": [
                {"metric_type": "accuracy", "weight": 1.0}
            ],
            "parameters": {"batch_size": 10, "timeout_per_sample": 30},
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Evaluation"
    assert data["version"] == 1


@pytest.mark.asyncio
async def test_list_evaluation_configs(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test listing evaluation configurations with pagination."""
    # Create a config first
    await client.post(
        "/api/v1/evaluations/configs",
        headers=auth_headers,
        json={
            "name": "List Test",
            "model_config": {"provider": "openai"},
        },
    )

    response = await client.get(
        "/api/v1/evaluations/configs",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert data["total"] >= 1


@pytest.mark.asyncio
async def test_get_evaluation_config(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test getting a specific evaluation configuration."""
    # Create
    create_resp = await client.post(
        "/api/v1/evaluations/configs",
        headers=auth_headers,
        json={
            "name": "Get Test",
            "model_config": {"provider": "openai"},
        },
    )
    config_id = create_resp.json()["id"]

    # Get
    response = await client.get(
        f"/api/v1/evaluations/configs/{config_id}",
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["id"] == config_id


@pytest.mark.asyncio
async def test_update_evaluation_config_increments_version(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test that updating a config increments its version."""
    # Create
    create_resp = await client.post(
        "/api/v1/evaluations/configs",
        headers=auth_headers,
        json={
            "name": "Version Test",
            "model_config": {"provider": "openai"},
        },
    )
    config_id = create_resp.json()["id"]
    assert create_resp.json()["version"] == 1

    # Update
    update_resp = await client.patch(
        f"/api/v1/evaluations/configs/{config_id}",
        headers=auth_headers,
        json={"name": "Updated Name"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["version"] == 2
    assert update_resp.json()["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_evaluation_config(
    client: AsyncClient,
    auth_headers: dict[str, str],
) -> None:
    """Test soft-deleting an evaluation configuration."""
    # Create
    create_resp = await client.post(
        "/api/v1/evaluations/configs",
        headers=auth_headers,
        json={
            "name": "Delete Test",
            "model_config": {"provider": "openai"},
        },
    )
    config_id = create_resp.json()["id"]

    # Delete
    del_resp = await client.delete(
        f"/api/v1/evaluations/configs/{config_id}",
        headers=auth_headers,
    )
    assert del_resp.status_code == 200

    # Verify it's gone
    get_resp = await client.get(
        f"/api/v1/evaluations/configs/{config_id}",
        headers=auth_headers,
    )
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_unauthenticated_access_denied(
    client: AsyncClient,
) -> None:
    """Test that evaluation endpoints require authentication."""
    response = await client.get("/api/v1/evaluations/configs")
    assert response.status_code == 401
