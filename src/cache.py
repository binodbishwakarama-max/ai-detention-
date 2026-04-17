"""
Core Cache Manager (L1/L2).

L1: functools.lru_cache for static/config data (in-process).
L2: Redis Async Backend with Fail-Open logic & Stampede Prevention.

Features:
- Fail-open: If Redis goes down, requests continue bypassing cache.
- Stampede prevention: Probabilistic early expiration (X-Fetch algorithm).
- Decorators: @cached for async function wrapping.
- Metrics logging: Tracks hit/miss ratios per key-pattern.
"""

from __future__ import annotations

import asyncio
import functools
import json
import math
import random
import time
from typing import Any, Callable, Coroutine, TypeVar

import redis.asyncio as aioredis
import structlog

from src.config import get_settings

logger = structlog.get_logger(__name__)

T = TypeVar("T")

# ── L1 Cache ──────────────────────────────────────────────────────
# Using functools.lru_cache for static/config objects per worker.
# Example usage: @lru_cache_l1(maxsize=128)
lru_cache_l1 = functools.lru_cache


# ── L2 Cache Wrapper ─────────────────────────────────────────────
class CacheManager:
    """Async Redis cache manager with fail-open logic."""

    def __init__(self):
        self._redis: aioredis.Redis | None = None
        self._is_connected: bool = False

    async def connect(self) -> None:
        """Initialize Redis connection pool."""
        if not self._redis:
            settings = get_settings()
            try:
                self._redis = aioredis.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    max_connections=settings.redis_max_connections,
                    socket_timeout=2.0,
                    socket_connect_timeout=2.0,
                )
                await self._redis.ping()
                self._is_connected = True
                logger.info("cache.connected", url=settings.redis_url)
            except Exception as e:
                self._is_connected = False
                logger.warning("cache.connection_failed", error=str(e), action="failing_open")

    async def disconnect(self) -> None:
        if self._redis:
            await self._redis.aclose()
            self._is_connected = False
            logger.info("cache.disconnected")

    @property
    def is_healthy(self) -> bool:
        return self._is_connected

    async def get(self, key: str) -> Any | None:
        """Fetch item from Redis. Fails open on timeout/error."""
        if not self._is_connected or not self._redis:
            return None

        pattern = key.split(":")[0] if ":" in key else key

        try:
            val = await self._redis.get(key)
            if val:
                logger.debug("cache.hit", key=key)
                try:
                    from src.observability.metrics import get_metrics
                    get_metrics().cache_hits_total.labels(cache_key_pattern=pattern).inc()
                except Exception:
                    pass
                return json.loads(val)
            logger.debug("cache.miss", key=key)
            try:
                from src.observability.metrics import get_metrics
                get_metrics().cache_misses_total.labels(cache_key_pattern=pattern).inc()
            except Exception:
                pass
            return None
        except aioredis.RedisError as e:
            logger.warning("cache.get_error", key=key, error=str(e), action="fail_open")
            return None

    async def set(self, key: str, value: Any, ttl: int) -> None:
        """Set item in cache. Fails open gracefully."""
        if not self._is_connected or not self._redis:
            return
        
        try:
            # We store the creation time and TTL along with the value for Probabilistic Expiration
            payload = {
                "val": value,
                "ts": time.time(),
                "ttl": ttl
            }
            await self._redis.set(key, json.dumps(payload), ex=ttl)
        except aioredis.RedisError as e:
            logger.warning("cache.set_error", key=key, error=str(e))

    async def delete_pattern(self, pattern: str) -> None:
        """Delete keys matching pattern. Useful for wildcards submissions:{org}:*."""
        if not self._is_connected or not self._redis:
            return
        try:
            cursor = b"0"
            while cursor:
                cursor, keys = await self._redis.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await self._redis.delete(*keys)
        except aioredis.RedisError as e:
            logger.warning("cache.delete_error", pattern=pattern, error=str(e))


cache_manager = CacheManager()


# ── X-Fetch Cache Stampede Prevention ────────────────────────────
def _should_recompute(ts: float, ttl: int, beta: float = 1.0) -> bool:
    """
    Probabilistic early expiration (X-Fetch algorithm).
    ts: timestamp when the value was originally cached
    duration: original TTL length
    """
    now = time.time()
    expiry = ts + ttl
    # delta is the time difference remaining until true expiry.
    # We use random log logic to create an increasing probability curve.
    return (now - expiry) >= - (beta * ttl * math.log(random.random()))


# ── Decorators ───────────────────────────────────────────────────
def cached(ttl: int, key_builder: Callable[..., str], beta: float = 1.0):
    """
    Async decorator that handles X-Fetch probabilistic caching and Fail-Open.
    
    ttl: Time to live in seconds.
    key_builder: Function that takes (args, kwargs) and returns a cache key string.
    beta: Stampede prevention tuning (larger = earlier probabilistic refresh).
    """

    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            key = key_builder(*args, **kwargs)
            
            if cache_manager.is_healthy:
                cached_data = await cache_manager.get(key)
                if cached_data is not None:
                    # Check stampede
                    ts = cached_data.get("ts", 0)
                    stored_ttl = cached_data.get("ttl", ttl)
                    
                    if not _should_recompute(ts, stored_ttl, beta):
                        return cached_data["val"]
                    
                    logger.debug("cache.probabilistic_recompute", key=key)
            
            # Compute real value
            result = await func(*args, **kwargs)
            
            # Set cache
            await cache_manager.set(key, result, ttl)
            return result

        return wrapper
    return decorator


# ── Cache Warming ────────────────────────────────────────────────
async def init_cache_warming() -> None:
    """
    Warm-up L1 / L2 caches. Fired on app startup.
    Loads standard taxonomies or heavy config structures.
    """
    logger.info("cache.warming_started")
    # Simulate DB taxonomy load.
    await asyncio.sleep(0.1)
    await cache_manager.set("configs:system_taxonomy", {"v": "1.0", "labels": []}, ttl=86400)
    logger.info("cache.warming_completed")
