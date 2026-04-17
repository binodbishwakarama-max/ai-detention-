"""
Celery application — production-grade configuration.

Queue Architecture:
┌──────────────┬─────────────┬────────────────────────────────────────┐
│ Queue        │ Concurrency │ Tasks                                  │
├──────────────┼─────────────┼────────────────────────────────────────┤
│ high_priority│ 4           │ evaluate_submission, finalize_and_notify│
│ analysis     │ 10          │ github, pitch_deck, video, web_verify  │
│ ai_inference │ 4           │ cross_check, fabrication, llm_judge    │
│ export       │ 2           │ result exports, report generation      │
└──────────────┴─────────────┴────────────────────────────────────────┘

Reliability guarantees:
- acks_late=True: task ACK'd AFTER completion (at-least-once delivery)
- reject_on_worker_lost=True: re-queue on worker crash
- task_acks_on_failure_or_timeout=False: failed tasks stay for inspection
- worker_max_tasks_per_child=100: restart process to prevent memory leaks
- Results stored in PostgreSQL (not Redis) for durability
"""

from __future__ import annotations

from celery import Celery
from kombu import Exchange, Queue

from src.config import get_settings

settings = get_settings()

# ── Create Celery App ────────────────────────────────────────
celery_app = Celery(
    "eval-engine",
    broker=settings.celery_broker_url,
    # Results go to PostgreSQL for durability (not volatile Redis)
    backend=f"db+{settings.database_url.replace('+asyncpg', '')}",
)

# ── Exchange & Queue Definitions ─────────────────────────────
default_exchange = Exchange("eval_engine", type="direct")

celery_app.conf.task_queues = (
    Queue("high_priority", default_exchange, routing_key="high_priority"),
    Queue("analysis", default_exchange, routing_key="analysis"),
    Queue("ai_inference", default_exchange, routing_key="ai_inference"),
    Queue("export", default_exchange, routing_key="export"),
)

celery_app.conf.task_default_queue = "analysis"
celery_app.conf.task_default_exchange = "eval_engine"
celery_app.conf.task_default_routing_key = "analysis"

# ── Task Routing ─────────────────────────────────────────────
celery_app.conf.task_routes = {
    # High priority: orchestration and finalization
    "src.workers.tasks.orchestrator.evaluate_submission": {"queue": "high_priority"},
    "src.workers.tasks.finalize.finalize_and_notify_task": {"queue": "high_priority"},
    # Analysis: parallel data extraction tasks
    "src.workers.tasks.github_analysis.github_analysis_task": {"queue": "analysis"},
    "src.workers.tasks.pitch_deck.pitch_deck_task": {"queue": "analysis"},
    "src.workers.tasks.video_analysis.video_analysis_task": {"queue": "analysis"},
    "src.workers.tasks.web_verification.web_verification_task": {"queue": "analysis"},
    # AI inference: GPU/LLM-bound tasks
    "src.workers.tasks.cross_check.cross_check_task": {"queue": "ai_inference"},
    "src.workers.tasks.fabrication.fabrication_detection_task": {"queue": "ai_inference"},
    "src.workers.tasks.llm_judge.llm_judge_task": {"queue": "ai_inference"},
    # Export
    "src.workers.tasks.export.export_results_task": {"queue": "export"},
}

# ── Serialization ────────────────────────────────────────────
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

# ── Reliability ──────────────────────────────────────────────
celery_app.conf.update(
    # ACK after completion, not on receipt — at-least-once delivery
    task_acks_late=True,
    # Re-queue task if worker process crashes (OOM, SIGKILL)
    task_reject_on_worker_lost=True,
    # Don't ACK failed tasks — keep them for inspection
    task_acks_on_failure_or_timeout=False,
    # Store task results for 7 days in PostgreSQL
    result_expires=604800,
    # Track task lifecycle events (started, succeeded, failed)
    task_track_started=True,
    task_send_sent_event=True,
)

# ── Timeouts (global defaults, overridden per-task) ──────────
celery_app.conf.update(
    task_soft_time_limit=300,   # 5 min soft limit (raises SoftTimeLimitExceeded)
    task_time_limit=360,        # 6 min hard limit (SIGKILL)
)

# ── Performance & Memory ─────────────────────────────────────
celery_app.conf.update(
    # One task at a time per process — prevents memory spikes
    worker_prefetch_multiplier=1,
    # Default concurrency (overridden per-queue at startup)
    worker_concurrency=4,
    # Restart worker process after 100 tasks to prevent memory leaks
    worker_max_tasks_per_child=100,
    # Max memory per worker before restart (500MB)
    worker_max_memory_per_child=512000,
)

# ── Retry Policy (global defaults) ──────────────────────────
celery_app.conf.update(
    task_default_retry_delay=2,
    task_max_retries=3,
)

# ── Dead Letter Queue ────────────────────────────────────────
# Tasks that exhaust all retries are published to DLQ
celery_app.conf.task_reject_on_worker_lost = True

# ── Auto-discover Tasks ─────────────────────────────────────
celery_app.autodiscover_tasks([
    "src.workers.tasks.orchestrator",
    "src.workers.tasks.github_analysis",
    "src.workers.tasks.pitch_deck",
    "src.workers.tasks.video_analysis",
    "src.workers.tasks.web_verification",
    "src.workers.tasks.cross_check",
    "src.workers.tasks.fabrication",
    "src.workers.tasks.llm_judge",
    "src.workers.tasks.finalize",
    "src.workers.tasks.export",
])


# ── Observability: Celery Signal Handlers ────────────────────────

import time as _time_mod

from celery.signals import task_failure, task_postrun, task_prerun, worker_process_init

@worker_process_init.connect
def _on_worker_process_init(**kwargs):
    """
    Initialize OpenTelemetry tracing in the worker child process.
    Must be done after forking to ensure proper reporting.
    """
    try:
        from src.observability.tracing import init_tracing
        init_tracing(
            service_name=f"{settings.otel_service_name}-worker",
            exporter_type=settings.otel_exporter,
            endpoint=settings.otel_endpoint,
            sample_rate=settings.otel_sample_rate,
            enabled=settings.otel_enabled,
        )
    except Exception:
        pass

_task_start_times: dict[str, float] = {}


def _short_task_name(name: str) -> str:
    """Extract the short task name from the fully qualified path."""
    return name.rsplit(".", 1)[-1] if "." in name else name


@task_prerun.connect
def _on_task_prerun(sender=None, task_id=None, **kwargs):
    """Record the task start time for duration calculation."""
    _task_start_times[task_id] = _time_mod.perf_counter()


@task_postrun.connect
def _on_task_postrun(sender=None, task_id=None, state=None, **kwargs):
    """Observe task duration and increment task counters on completion."""
    start = _task_start_times.pop(task_id, None)
    if start is None:
        return

    duration = _time_mod.perf_counter() - start
    task_name = _short_task_name(sender.name) if sender else "unknown"
    status = state or "SUCCESS"

    try:
        from src.observability.metrics import get_metrics

        metrics = get_metrics()
        metrics.celery_task_duration_seconds.labels(
            task_name=task_name, status=status
        ).observe(duration)
        metrics.celery_tasks_total.labels(
            task_name=task_name, status=status
        ).inc()
    except Exception:
        pass  # Metrics unavailable — fail open


@task_failure.connect
def _on_task_failure(sender=None, task_id=None, exception=None, **kwargs):
    """Record failed task metrics and clean up start time."""
    start = _task_start_times.pop(task_id, None)
    if start is None:
        return

    duration = _time_mod.perf_counter() - start
    task_name = _short_task_name(sender.name) if sender else "unknown"

    try:
        from src.observability.metrics import get_metrics

        metrics = get_metrics()
        metrics.celery_task_duration_seconds.labels(
            task_name=task_name, status="FAILURE"
        ).observe(duration)
        metrics.celery_tasks_total.labels(
            task_name=task_name, status="FAILURE"
        ).inc()
    except Exception:
        pass


# ── Periodic Queue Depth Polling ─────────────────────────────────

celery_app.conf.beat_schedule = {
    "poll-queue-depth": {
        "task": "src.workers.celery_app.poll_queue_depth",
        "schedule": 30.0,  # Every 30 seconds
    },
}


@celery_app.task(name="src.workers.celery_app.poll_queue_depth", ignore_result=True)
def poll_queue_depth():
    """Periodic task that reads queue lengths from Redis and updates gauges."""
    import redis as sync_redis

    try:
        from src.observability.metrics import get_metrics

        metrics = get_metrics()
        r = sync_redis.from_url(settings.celery_broker_url)

        for queue_name in ("high_priority", "analysis", "ai_inference", "export"):
            try:
                depth = r.llen(queue_name)
                metrics.celery_queue_depth.labels(queue_name=queue_name).set(depth)
            except Exception:
                pass
        r.close()
    except Exception:
        pass

