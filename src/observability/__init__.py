"""
Production observability package.

Three pillars:
1. Structured Logging (structlog + JSON + field masking)
2. Metrics (Prometheus counters, histograms, gauges)
3. Distributed Tracing (OpenTelemetry → Jaeger / Cloud Trace)
"""

from src.observability.logging import configure_logging
from src.observability.metrics import get_metrics
from src.observability.tracing import init_tracing

__all__ = ["configure_logging", "get_metrics", "init_tracing"]
