"""Integration tests for rate limiter middleware."""

from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest
from httpx import AsyncClient

from src.main import app
from src.middleware.rate_limiter import setup_rate_limiter


@pytest.mark.asyncio
async def test_rate_limiting_enforcement(client: AsyncClient, mock_redis):
    """
    Test that the rate limiter correctly enforces limits and returns 429.
    
    We need to configure the rate limiter to a very low limit to easily hit it,
    or mock the redis check to simulate limit exceeded.
    """
    # Rate limiter is initialized in app lifespan. 
    # To test it, we mock the increment behavior in Redis.
    
    with patch("src.middleware.rate_limiter.get_redis") as mock_get_redis:
        mock_r = mock_get_redis.return_value
        
        # Simulate hitting the limit on the second request
        # First request: 1 (limit is 30, so this passes)
        # Second request: 31 (exceeds limit)
        mock_r.incr.side_effect = [1, 31]
        mock_r.ttl.return_value = 60
        mock_r.expire.return_value = True

        # First request should pass
        res1 = await client.get("/health/live")
        assert res1.status_code == 200

        # Second request should fail with 429
        # (Assuming /health is not exempt in this specific mocked environment,
        # actually /health is exempted. Let's use a non-exempt path)
        res_pass = await client.get("/api/v1/metrics", headers={"X-Forwarded-For": "1.2.3.4"})
        assert res_pass.status_code == 401  # Passes rate limiter, hits Auth

        mock_r.incr.side_effect = [31] # next one fails
        res_fail = await client.get("/api/v1/metrics", headers={"X-Forwarded-For": "1.2.3.4"})
        assert res_fail.status_code == 429
        
        data = res_fail.json()
        assert "Rate limit exceeded" in data["detail"]

@pytest.mark.asyncio
async def test_exempt_endpoints(client: AsyncClient, mock_redis):
    """Test that health endpoints bypass the rate limiter."""
    with patch("src.middleware.rate_limiter.get_redis") as mock_get_redis:
        mock_r = mock_get_redis.return_value
        mock_r.incr.return_value = 1000 # Way over any limit
        
        # Health should still return 200 because it's exempt
        res = await client.get("/health/live")
        assert res.status_code == 200
        
        # Redis incr should never be called for exempt paths
        mock_r.incr.assert_not_called()
