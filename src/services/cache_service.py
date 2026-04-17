"""
Redis cache service with typed helpers.

Provides a consistent caching interface with:
- Automatic JSON serialization/deserialization via orjson
- Configurable TTL per cache entry
- Cache invalidation by key pattern (using SCAN, not KEYS)
- Namespace isolation to prevent key collisions
- Fail-open strategy: cache errors never break the application

Cache key format: "eval-engine:{namespace}:{key}"
"""

from __future__ import annotations

from typing import Any

import orjson
import structlog

from src.config import get_settings
from src.redis_client import get_redis

logger = structlog.get_logger(__name__)

# Cache key prefix for namespace isolation
PREFIX = "eval-engine"


async def cache_get(namespace: str, key: str) -> Any | None:
    """
    Get a cached value by namespace and key.

    Returns None on cache miss or Redis errors (fail-open strategy:
    cache failures should never break the application).
    """
    try:
        redis = await get_redis()
        raw = await redis.get(f"{PREFIX}:{namespace}:{key}")
        if raw is None:
            return None
        return orjson.loads(raw)
    except Exception:
        logger.warning(
            "cache.get_failed", namespace=namespace, key=key
        )
        return None


async def cache_set(
    namespace: str,
    key: str,
    value: Any,
    ttl: int | None = None,
) -> None:
    """
    Set a cached value with optional TTL.

    If TTL is not provided, uses the default from settings.
    Values are serialized to JSON via orjson (3-10x faster than stdlib json).
    """
    try:
        settings = get_settings()
        redis = await get_redis()
        serialized = orjson.dumps(value).decode("utf-8")
        await redis.set(
            f"{PREFIX}:{namespace}:{key}",
            serialized,
            ex=ttl or settings.redis_cache_ttl,
        )
    except Exception:
        logger.warning(
            "cache.set_failed", namespace=namespace, key=key
        )


async def cache_delete(namespace: str, key: str) -> None:
    """Delete a specific cached value."""
    try:
        redis = await get_redis()
        await redis.delete(f"{PREFIX}:{namespace}:{key}")
    except Exception:
        logger.warning(
            "cache.delete_failed", namespace=namespace, key=key
        )


async def cache_invalidate_pattern(
    namespace: str, pattern: str = "*"
) -> int:
    """
    Invalidate all cache entries matching a pattern within a namespace.

    Uses SCAN instead of KEYS to avoid blocking Redis on large keyspaces.
    Returns the number of deleted keys.
    """
    try:
        redis = await get_redis()
        full_pattern = f"{PREFIX}:{namespace}:{pattern}"
        deleted = 0
        async for key in redis.scan_iter(
            match=full_pattern, count=100
        ):
            await redis.delete(key)
            deleted += 1
        return deleted
    except Exception:
        logger.warning(
            "cache.invalidate_failed",
            namespace=namespace,
            pattern=pattern,
        )
        return 0
