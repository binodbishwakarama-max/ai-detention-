"""
Request correlation ID middleware.

Generates a unique ID for each incoming request and propagates it through:
- Response headers (X-Request-ID)
- Log context (structlog contextvars)
- OpenTelemetry span attributes
- Downstream service calls
- Celery task metadata

This enables end-to-end request tracing across the entire system:
API Gateway → FastAPI → Celery Worker → Webhook callback
"""

from __future__ import annotations

import time
import uuid
from contextvars import ContextVar

import structlog
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response

# Context variable for request-scoped correlation ID.
# Using contextvars ensures each async task gets its own ID,
# even under concurrent request processing.
correlation_id_ctx: ContextVar[str] = ContextVar(
    "correlation_id", default=""
)


def get_correlation_id() -> str:
    """Get the current request's correlation ID."""
    return correlation_id_ctx.get()


class CorrelationMiddleware(BaseHTTPMiddleware):
    """
    Assigns a unique correlation ID to each request.

    If the client sends X-Request-ID, we use it (useful for tracing
    across client → API boundaries). Otherwise, we generate a new one.

    Also binds request context (request_id, user_id, org_id) into
    structlog contextvars so all downstream log lines automatically
    include them.
    """

    HEADER_NAME = "X-Request-ID"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Reuse client-provided ID if present, else generate new
        request_id = request.headers.get(
            self.HEADER_NAME, str(uuid.uuid4())
        )

        # Set in context var so all downstream code can access it
        token = correlation_id_ctx.set(request_id)

        # Bind request context into structlog for automatic inclusion
        # in all log lines within this request scope.
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            request_id=request_id,
            method=request.method,
            path=request.url.path,
        )

        start_time = time.perf_counter()

        try:
            response = await call_next(request)

            # After auth resolves, bind user/org context for remaining logs
            user_id = getattr(request.state, "user_id", None)
            org_id = getattr(request.state, "org_id", None)
            if user_id:
                structlog.contextvars.bind_contextvars(
                    user_id=user_id,
                    org_id=org_id,
                )

            # Add duration to the response context
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            structlog.contextvars.bind_contextvars(duration_ms=duration_ms)

            # Echo the correlation ID back to the client
            response.headers[self.HEADER_NAME] = request_id
            return response
        finally:
            # Reset context var to prevent leaking to other requests
            correlation_id_ctx.reset(token)
            structlog.contextvars.clear_contextvars()
