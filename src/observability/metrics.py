"""
Prometheus metrics registry.

All application metrics are defined here as a single source of truth.
Consumers import `get_metrics()` and access named attributes.

Naming follows Prometheus conventions:
  <namespace>_<subsystem>_<name>_<unit>
  Labels use snake_case and are low-cardinality.

Metric categories:
  HTTP       — Request throughput, latency, error rates
  Celery     — Task duration, queue depth
  LLM        — Token usage, cost tracking
  Cache      — Hit/miss ratios
  Database   — Query duration by type
  Business   — Active evaluation gauge
"""

from __future__ import annotations

from functools import lru_cache

from prometheus_client import Counter, Gauge, Histogram

# ── Histogram bucket definitions ─────────────────────────────────

# HTTP latency: 10ms → 10s covers API responses
HTTP_DURATION_BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)

# Celery task duration: 100ms → 600s covers all task types
CELERY_DURATION_BUCKETS = (0.1, 0.5, 1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0)

# DB query duration: 1ms → 5s
DB_DURATION_BUCKETS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 5.0)


class MetricsRegistry:
    """
    Singleton holding all Prometheus metric objects.

    Using a class (vs module-level globals) allows controlled
    initialization and makes testing with fresh registries possible.
    """

    def __init__(self) -> None:
        # ── HTTP Metrics ─────────────────────────────────────────
        self.http_requests_total = Counter(
            "http_requests_total",
            "Total HTTP requests processed",
            ["method", "endpoint", "status_code"],
        )
        self.http_request_duration_seconds = Histogram(
            "http_request_duration_seconds",
            "HTTP request latency in seconds",
            ["method", "endpoint"],
            buckets=HTTP_DURATION_BUCKETS,
        )
        self.http_requests_in_progress = Gauge(
            "http_requests_in_progress",
            "Number of HTTP requests currently being processed",
            ["method"],
        )

        # ── Celery Metrics ───────────────────────────────────────
        self.celery_task_duration_seconds = Histogram(
            "celery_task_duration_seconds",
            "Celery task execution duration in seconds",
            ["task_name", "status"],
            buckets=CELERY_DURATION_BUCKETS,
        )
        self.celery_tasks_total = Counter(
            "celery_tasks_total",
            "Total Celery tasks processed",
            ["task_name", "status"],
        )
        self.celery_queue_depth = Gauge(
            "celery_queue_depth",
            "Number of messages in each Celery queue",
            ["queue_name"],
        )

        # ── LLM Metrics ─────────────────────────────────────────
        self.llm_tokens_used_total = Counter(
            "llm_tokens_used_total",
            "Total LLM tokens consumed",
            ["model", "task_type"],
        )
        self.llm_cost_usd_total = Counter(
            "llm_cost_usd_total",
            "Total LLM inference cost in USD",
            ["model", "task_type"],
        )

        # ── Cache Metrics ────────────────────────────────────────
        self.cache_hits_total = Counter(
            "cache_hits_total",
            "Total cache hits",
            ["cache_key_pattern"],
        )
        self.cache_misses_total = Counter(
            "cache_misses_total",
            "Total cache misses",
            ["cache_key_pattern"],
        )

        # ── Database Metrics ─────────────────────────────────────
        self.db_query_duration_seconds = Histogram(
            "db_query_duration_seconds",
            "Database query duration in seconds",
            ["query_type"],
            buckets=DB_DURATION_BUCKETS,
        )

        # ── Business Metrics ─────────────────────────────────────
        self.active_evaluations_gauge = Gauge(
            "active_evaluations_gauge",
            "Number of evaluations currently running",
        )


@lru_cache(maxsize=1)
def get_metrics() -> MetricsRegistry:
    """Return the singleton metrics registry."""
    return MetricsRegistry()
