"""
Rate Limiting logic via Redis Sliding Window.

Uses a Redis sorted set (ZSET) to track timestamped events.
Format: `ratelimit:{user_id}:{endpoint}:{window_seconds}`
"""

from __future__ import annotations

import time

import structlog

from src.cache import cache_manager

logger = structlog.get_logger(__name__)


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__(f"Rate limit exceeded. Try again in {retry_after}s.")


async def check_rate_limit(
    identifier: str, 
    endpoint: str, 
    limit: int, 
    window_seconds: int = 60
) -> None:
    """
    Sliding window log algorithm via Redis.
    
    If Redis fails, we fail OPEN (allow the request). 
    We prioritize availability over strict limiting during outages.
    """
    if not cache_manager.is_healthy or not cache_manager._redis:
        logger.debug("ratelimit.skipped_redis_down")
        return

    now = time.time()
    clear_before = now - window_seconds
    key = f"ratelimit:{identifier}:{endpoint}:{window_seconds}"
    
    try:
        pipeline = cache_manager._redis.pipeline()
        # 1. Remove timestamps older than the window
        pipeline.zremrangebyscore(key, 0, clear_before)
        # 2. Add current timestamp
        pipeline.zadd(key, {str(now): now})
        # 3. Count remaining elements in the window
        pipeline.zcard(key)
        # 4. Set expiry tightly to the window to avoid stale keys eating RAM
        pipeline.expire(key, window_seconds + 5)
        
        results = await pipeline.execute()
        current_requests = results[2]
        
        if current_requests > limit:
            logger.warning("ratelimit.exceeded", identifier=identifier, endpoint=endpoint)
            # Find the oldest entry to calculate precise 'retry-after'
            oldest = await cache_manager._redis.zrange(key, 0, 0, withscores=True)
            retry_after = window_seconds
            if oldest:
                oldest_ts = oldest[0][1]
                retry_after = max(1, int((oldest_ts + window_seconds) - now))
            
            raise RateLimitExceeded(retry_after)
            
    except RateLimitExceeded:
        raise
    except Exception as e:
        logger.error("ratelimit.redis_error_fail_open", error=str(e))
        return
