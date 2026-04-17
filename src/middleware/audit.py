"""
Audit logging middleware.

Captures every mutating operation (POST, PUT, PATCH, DELETE) and logs it
with structured fields. Read operations (GET) are not logged by default
to avoid excessive log volume, but can be enabled per-endpoint.

The middleware extracts:
- User identity (from JWT or API key)
- Client IP and User-Agent
- Correlation ID (from CorrelationMiddleware)
- Request method, path, and status code

Detailed before/after changes are logged at the service layer, not here.
"""

from __future__ import annotations

import time

import structlog
from starlette.middleware.base import (
    BaseHTTPMiddleware,
    RequestResponseEndpoint,
)
from starlette.requests import Request
from starlette.responses import Response

from src.middleware.correlation import get_correlation_id

logger = structlog.get_logger(__name__)

# Methods that trigger audit logging
AUDITABLE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class AuditMiddleware(BaseHTTPMiddleware):
    """
    Middleware that logs all mutating API operations.

    Audit entries include request metadata and are correlated with
    the request ID for end-to-end tracing.
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Only audit mutating operations
        if request.method not in AUDITABLE_METHODS:
            return await call_next(request)

        start_time = time.monotonic()

        # Extract request metadata
        client_ip = (
            request.client.host if request.client else "unknown"
        )
        user_agent = request.headers.get("User-Agent", "unknown")
        correlation_id = get_correlation_id()

        try:
            response = await call_next(request)
            duration_ms = (time.monotonic() - start_time) * 1000

            # Log the audit event
            logger.info(
                "api.audit",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
                client_ip=client_ip,
                user_agent=user_agent,
                request_id=correlation_id,
                user_id=getattr(request.state, "user_id", None),
                org_id=getattr(request.state, "org_id", None),
            )

            return response

        except Exception as exc:
            duration_ms = (time.monotonic() - start_time) * 1000
            logger.error(
                "api.audit.error",
                method=request.method,
                path=request.url.path,
                error=str(exc),
                duration_ms=round(duration_ms, 2),
                client_ip=client_ip,
                request_id=correlation_id,
            )
            raise
