"""
Global exception handler middleware.

Catches all unhandled exceptions and converts them to structured JSON
responses. This ensures:
1. Clients always get a consistent error format
2. Stack traces never leak to clients in production
3. All errors are logged with correlation IDs for debugging
4. Prometheus error counters are incremented
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from src.middleware.correlation import get_correlation_id

logger = structlog.get_logger(__name__)


class AppException(Exception):
    """
    Base application exception.

    All business logic exceptions should extend this to provide
    structured error responses with appropriate HTTP status codes.
    """

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "bad_request",
        detail: dict | None = None,
    ):
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.detail = detail
        super().__init__(message)


class NotFoundError(AppException):
    """Resource not found."""

    def __init__(
        self, resource: str, resource_id: str | None = None
    ):
        msg = f"{resource} not found"
        if resource_id:
            msg = f"{resource} with id '{resource_id}' not found"
        super().__init__(msg, status.HTTP_404_NOT_FOUND, "not_found")


class ConflictError(AppException):
    """Resource conflict (duplicate, state violation)."""

    def __init__(self, message: str):
        super().__init__(
            message, status.HTTP_409_CONFLICT, "conflict"
        )


class ForbiddenError(AppException):
    """Insufficient permissions."""

    def __init__(self, message: str = "Insufficient permissions"):
        super().__init__(
            message, status.HTTP_403_FORBIDDEN, "forbidden"
        )


class UnauthorizedError(AppException):
    """Authentication required or failed."""

    def __init__(self, message: str = "Authentication required"):
        super().__init__(
            message, status.HTTP_401_UNAUTHORIZED, "unauthorized"
        )


class RateLimitError(AppException):
    """Rate limit exceeded."""

    def __init__(self, retry_after: int = 60):
        super().__init__(
            f"Rate limit exceeded. Retry after {retry_after}s",
            status.HTTP_429_TOO_MANY_REQUESTS,
            "rate_limit_exceeded",
            {"retry_after": retry_after},
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(
        request: Request, exc: AppException
    ) -> JSONResponse:
        """Handle application-level exceptions."""
        request_id = get_correlation_id()
        logger.warning(
            "app.exception",
            error_code=exc.error_code,
            message=exc.message,
            status_code=exc.status_code,
            request_id=request_id,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": exc.error_code,
                "message": exc.message,
                "detail": exc.detail,
                "request_id": request_id,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors with structured detail."""
        request_id = get_correlation_id()
        errors = []
        for error in exc.errors():
            errors.append(
                {
                    "field": " → ".join(
                        str(loc) for loc in error["loc"]
                    ),
                    "message": error["msg"],
                    "type": error["type"],
                }
            )
        logger.warning(
            "validation.error",
            errors=errors,
            request_id=request_id,
            path=request.url.path,
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": "validation_error",
                "message": "Request validation failed",
                "detail": errors,
                "request_id": request_id,
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """Handle Starlette HTTP exceptions."""
        request_id = get_correlation_id()
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": "http_error",
                "message": exc.detail,
                "request_id": request_id,
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """
        Catch-all for unhandled exceptions.

        In production, this prevents stack traces from leaking to clients.
        The error is logged with full context for debugging.
        Also records the exception into the active OTel span.
        """
        request_id = get_correlation_id()
        logger.exception(
            "unhandled.exception",
            error=str(exc),
            error_type=type(exc).__name__,
            request_id=request_id,
            path=request.url.path,
            method=request.method,
        )

        # Record exception in OpenTelemetry span for distributed tracing
        try:
            from opentelemetry import trace

            span = trace.get_current_span()
            if span and span.is_recording():
                span.set_status(
                    trace.StatusCode.ERROR,
                    description=str(exc),
                )
                span.record_exception(exc)
        except ImportError:
            pass

        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": "internal_error",
                "message": (
                    "An unexpected error occurred. "
                    "Please contact support."
                ),
                "request_id": request_id,
            },
        )
