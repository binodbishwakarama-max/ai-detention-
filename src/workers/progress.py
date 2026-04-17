"""
Progress tracking utilities — Redis-backed real-time progress.

Provides a centralized way to query progress for all workers
in an evaluation run. Used by the API to serve progress to clients.
"""

from __future__ import annotations

from typing import Any

import redis
import structlog

from src.config import get_settings

logger = structlog.get_logger(__name__)

# All worker types in pipeline order
WORKER_TYPES = [
    "github_analysis",
    "pitch_deck",
    "video_analysis",
    "web_verification",
    "cross_check",
    "fabrication_detection",
    "llm_judge",
    "finalize",
]


def get_run_progress(run_id: str) -> dict[str, Any]:
    """
    Get progress for all workers in an evaluation run.

    Returns:
    {
        "overall_progress": 45,  # weighted average
        "workers": {
            "github_analysis": {"progress": 100, "detail": "Completed"},
            "pitch_deck": {"progress": 80, "detail": "Extracting claims"},
            ...
        }
    }
    """
    try:
        settings = get_settings()
        r = redis.from_url(settings.redis_url, decode_responses=True)

        workers = {}
        total_progress = 0

        for worker_type in WORKER_TYPES:
            key = f"progress:{run_id}:{worker_type}"
            data = r.hgetall(key)
            if data:
                prog = int(data.get("progress", 0))
                workers[worker_type] = {
                    "progress": prog,
                    "detail": data.get("detail", ""),
                    "updated_at": data.get("updated_at", ""),
                }
                total_progress += prog
            else:
                workers[worker_type] = {
                    "progress": 0,
                    "detail": "Not started",
                    "updated_at": "",
                }

        overall = total_progress // len(WORKER_TYPES) if WORKER_TYPES else 0

        return {
            "overall_progress": overall,
            "workers": workers,
        }

    except Exception:
        return {"overall_progress": 0, "workers": {}}


def get_dlq_entries(limit: int = 50) -> list[dict]:
    """Get recent Dead Letter Queue entries for monitoring."""
    try:
        settings = get_settings()
        r = redis.from_url(settings.redis_url, decode_responses=True)

        keys = r.lrange("dlq:all", 0, limit - 1)
        entries = []
        for key in keys:
            data = r.hgetall(key)
            if data:
                entries.append(data)

        return entries
    except Exception:
        return []


def retry_dlq_entry(run_id: str, worker_type: str) -> bool:
    """Re-queue a DLQ entry for retry."""
    try:
        settings = get_settings()
        r = redis.from_url(settings.redis_url, decode_responses=True)

        key = f"dlq:{run_id}:{worker_type}"
        data = r.hgetall(key)
        if not data:
            return False

        # Re-dispatch the task
        task_name = data.get("task_name", "")
        if task_name:
            from src.workers.celery_app import celery_app
            celery_app.send_task(task_name, args=[run_id])
            r.delete(key)
            r.lrem("dlq:all", 1, key)
            return True

        return False
    except Exception:
        return False
