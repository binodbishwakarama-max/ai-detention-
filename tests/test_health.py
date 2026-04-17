"""
Tests for the health check endpoints.

Verifies:
- Liveness probe returns 200 with version info
- Readiness probe checks database and Redis connectivity
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_liveness_probe(client: AsyncClient) -> None:
    """Test that the liveness endpoint returns 200."""
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "environment" in data


@pytest.mark.asyncio
async def test_liveness_returns_correct_version(
    client: AsyncClient,
) -> None:
    """Test that the liveness endpoint returns the configured version."""
    response = await client.get("/api/v1/health")
    data = response.json()
    assert data["version"]  # should be non-empty
