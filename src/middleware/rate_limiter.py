"""
Redis-backed sliding window rate limiter.

Uses a sliding window algorithm (not fixed window) for smoother rate enforcement:
- Fixed window: 100 req/min can burst 200 at the boundary
- Sliding window: 100 req/min is always 100 in any 60s period

Implementation uses Redis sorted sets with timestamps as scores:
1. Remove expired entries (older than window)
2. Count remaining entries
3. If under limit, add current timestamp
4. Return remaining quota in response headers

Per-organization limits are configurable via Organization.rate_limit_per_minute.
"""

from __future__ import annotations

import time

from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from src.config import get_settings
from src.redis_client import get_redis


class RateLimiterMiddleware(BaseHTTPMiddleware):
    """
    Sliding window rate limiter using Redis sorted sets.

    Rate limits are applied per-organization (identified by JWT org_id).
    Unauthenticated requests use the client IP as the rate limit key.
    """

    # Paths exempt from rate limiting
    EXEMPT_PATHS = {
        "/api/v1/health", "/api/v1/health/live",
        "/api/v1/health/ready", "/api/v1/health/deps",
        "/metrics",
    }

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip rate limiting for health checks and metrics
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)

        settings = get_settings()
        redis = await get_redis()

        # Extract rate limit identity: org_id from auth or client IP
        rate_key = self._get_rate_key(request)
        window = settings.rate_limit_window_seconds
        limit = settings.rate_limit_default

        now = time.time()
        window_start = now - window
        pipe_key = f"ratelimit:{rate_key}"

        # Atomic pipeline: clean expired + count + add in one round-trip
        async with redis.pipeline(transaction=True) as pipe:
            # Remove entries outside the current window
            pipe.zremrangebyscore(pipe_key, 0, window_start)
            # Count entries in the current window
            pipe.zcard(pipe_key)
            # Add current request timestamp
            pipe.zadd(pipe_key, {str(now): now})
            # Set TTL on the key to auto-cleanup
            pipe.expire(pipe_key, window + 1)
            results = await pipe.execute()

        current_count = results[1]  # zcard result

        # Standard rate limit response headers (RFC 6585 / draft)
        headers = {
            "X-RateLimit-Limit": str(limit),
            "X-RateLimit-Remaining": str(max(0, limit - current_count - 1)),
            "X-RateLimit-Reset": str(int(now + window)),
        }

        if current_count >= limit:
            return JSONResponse(
                status_code=429,
                content={
                    "error": "rate_limit_exceeded",
                    "message": (
                        f"Rate limit of {limit} requests "
                        f"per {window}s exceeded"
                    ),
                    "retry_after": window,
                },
                headers={**headers, "Retry-After": str(window)},
            )

        response = await call_next(request)
        # Add rate limit headers to successful responses too
        for key, value in headers.items():
            response.headers[key] = value
        return response

    def _get_rate_key(self, request: Request) -> str:
        """
        Extract the rate limit key from the request.

        Priority:
        1. Organization ID from JWT (for authenticated requests)
        2. Client IP address (for unauthenticated requests)
        """
        # Check for org_id in request state (set by auth dependency)
        org_id = getattr(request.state, "org_id", None)
        if org_id:
            return f"org:{org_id}"
        # Fallback to client IP
        client_ip = (
            request.client.host if request.client else "unknown"
        )
        return f"ip:{client_ip}"
