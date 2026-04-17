"""
Redis connection management with connection pooling.

Redis serves dual purpose in this system:
1. Cache layer — query results, user sessions, computed metrics
2. Message broker — Celery task queue (separate Redis DB)

Using hiredis parser for 2-3x faster response parsing on large payloads.
"""

from __future__ import annotations

import redis.asyncio as aioredis

from src.config import get_settings

# ── Connection Pool ─────────────────────────────────────────
_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """
    Return the global Redis connection pool.

    Using a single connection pool across the application ensures
    efficient connection reuse. The pool is lazily initialized on
    first call and reused for all subsequent calls.
    """
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = aioredis.from_url(
            settings.redis_url,
            max_connections=settings.redis_max_connections,
            decode_responses=True,  # return str instead of bytes
            retry_on_timeout=True,  # auto-retry on transient failures
            socket_keepalive=True,  # detect dead connections via TCP keepalive
            socket_connect_timeout=5,  # fail fast on connection issues
            health_check_interval=30,  # periodic health checks on idle connections
        )
    return _pool


async def close_redis() -> None:
    """Close the Redis connection pool. Called during application shutdown."""
    global _pool
    if _pool is not None:
        await _pool.aclose()
        _pool = None


async def redis_health_check() -> bool:
    """Check Redis connectivity. Used by health endpoint."""
    try:
        client = await get_redis()
        return await client.ping()
    except Exception:
        return False
