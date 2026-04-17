"""
HTTP metrics middleware.

Instruments every request with Prometheus counters and histograms:
  - http_requests_total{method, endpoint, status_code}
  - http_request_duration_seconds{method, endpoint}
  - http_requests_in_progress{method}

Path normalization:
  UUIDs in URL paths are replaced with `:id` to prevent label
  cardinality explosion. /api/v1/evaluations/runs/abc-123 becomes
  /api/v1/evaluations/runs/:id.

Excluded paths:
  /health/*, /metrics — prevent self-referential metric inflation.
"""

from __future__ import annotations

import re
import time

from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response

from src.observability.metrics import get_metrics

# UUID pattern for path normalization (v4 and general hex-dash patterns)
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
# Numeric IDs in paths
_NUMERIC_ID_RE = re.compile(r"/\d+(?=/|$)")

# Paths excluded from metrics collection
_EXCLUDED_PREFIXES = ("/health", "/metrics", "/docs", "/redoc", "/openapi.json")


def _normalize_path(path: str) -> str:
    """
    Replace dynamic path segments with placeholders.

    Examples:
        /api/v1/evaluations/runs/abc-def-123 → /api/v1/evaluations/runs/:id
        /api/v1/results/run/456 → /api/v1/results/run/:id
    """
    normalized = _UUID_RE.sub(":id", path)
    normalized = _NUMERIC_ID_RE.sub("/:id", normalized)
    return normalized


class MetricsMiddleware(BaseHTTPMiddleware):
    """
    Prometheus HTTP metrics collection middleware.

    Should be the outermost middleware (added first to the stack)
    to capture the full request lifecycle including auth and rate limiting.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Skip metrics for infrastructure endpoints
        if any(request.url.path.startswith(p) for p in _EXCLUDED_PREFIXES):
            return await call_next(request)

        metrics = get_metrics()
        method = request.method
        endpoint = _normalize_path(request.url.path)

        # Track in-progress requests
        metrics.http_requests_in_progress.labels(method=method).inc()
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            status_code = str(response.status_code)
        except Exception:
            status_code = "500"
            raise
        finally:
            duration = time.perf_counter() - start_time

            # Record metrics
            metrics.http_requests_total.labels(
                method=method, endpoint=endpoint, status_code=status_code
            ).inc()
            metrics.http_request_duration_seconds.labels(
                method=method, endpoint=endpoint
            ).observe(duration)
            metrics.http_requests_in_progress.labels(method=method).dec()

        return response
