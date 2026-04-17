"""
FastAPI application entry point.

This module creates and configures the FastAPI application with:
- Lifespan management (startup/shutdown hooks)
- Middleware stack (metrics → correlation → rate limiter → audit)
- Exception handlers
- CORS configuration
- Prometheus metrics endpoint
- OpenTelemetry distributed tracing
- Structured logging via structlog with field masking

The middleware stack is ordered intentionally:
1. MetricsMiddleware (outermost, captures full request lifecycle)
2. CorrelationMiddleware (sets request_id for all downstream)
3. RateLimiterMiddleware (early rejection saves resources)
4. AuditMiddleware (logs after auth is resolved)
"""

from __future__ import annotations

import logging
import sys
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import sentry_sdk
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import ORJSONResponse
from prometheus_client import (
    CollectorRegistry,
    generate_latest,
    multiprocess,
)
from starlette.responses import Response

from src.api.v1.router import v1_router
from src.config import get_settings
from src.database import dispose_engine, init_engine
from src.middleware.audit import AuditMiddleware
from src.middleware.correlation import CorrelationMiddleware
from src.middleware.error_handler import register_exception_handlers
from src.middleware.metrics import MetricsMiddleware
from src.middleware.rate_limiter import RateLimiterMiddleware
from src.observability.logging import configure_logging
from src.observability.tracing import init_tracing, shutdown_tracing
from src.redis_client import close_redis


def configure_sentry() -> None:
    """Initialize Sentry error tracking for production."""
    settings = get_settings()
    if settings.sentry_dsn:
        sentry_sdk.init(
            dsn=settings.sentry_dsn,
            environment=settings.app_env.value,
            release=f"eval-engine@{settings.app_version}",
            traces_sample_rate=0.1,  # 10% of requests traced
            profiles_sample_rate=0.1,
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.

    Startup:
    - Configure structured logging with field masking
    - Initialize OpenTelemetry tracing
    - Initialize database engine and connection pool
    - Verify Redis connectivity
    - Ensure S3 bucket exists
    - Seed built-in metrics

    Shutdown:
    - Dispose database connections
    - Close Redis pool
    - Flush and shutdown tracing
    """
    settings = get_settings()
    logger = structlog.get_logger(__name__)

    # ── Startup ──────────────────────────────────────────
    logger.info(
        "app.starting",
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.app_env.value,
    )

    # Initialize OpenTelemetry tracing
    init_tracing(
        service_name=settings.otel_service_name,
        exporter_type=settings.otel_exporter,
        endpoint=settings.otel_endpoint,
        sample_rate=settings.otel_sample_rate,
        enabled=settings.otel_enabled,
        app=app,
    )

    # Initialize database
    await init_engine()
    logger.info("app.database_initialized")

    # Verify Redis
    from src.redis_client import redis_health_check

    if await redis_health_check():
        logger.info("app.redis_connected")
    else:
        logger.warning("app.redis_unavailable")

    # Ensure S3 bucket
    try:
        from src.s3_client import ensure_bucket_exists

        ensure_bucket_exists()
        logger.info("app.s3_bucket_ready")
    except Exception:
        logger.warning("app.s3_unavailable")

    # Seed built-in metrics
    try:
        from src.database import get_standalone_session
        from src.services.metric_service import seed_builtin_metrics

        async with get_standalone_session() as db:
            count = await seed_builtin_metrics(db)
            if count:
                logger.info("app.metrics_seeded", count=count)
    except Exception:
        logger.warning("app.metric_seeding_failed")

    logger.info("app.started")

    yield

    # ── Shutdown ─────────────────────────────────────────
    logger.info("app.shutting_down")
    await dispose_engine()
    await close_redis()
    await shutdown_tracing()
    logger.info("app.shutdown_complete")


def create_app() -> FastAPI:
    """
    Factory function that creates and configures the FastAPI application.

    Using a factory function (instead of a module-level global) allows:
    - Testing with different configurations
    - Multiple app instances in the same process
    - Clean separation of configuration from instantiation
    """
    settings = get_settings()

    # Configure structured logging (with field masking and context enrichment)
    configure_logging(
        log_level=settings.log_level,
        log_format=settings.log_format,
        service_name=settings.otel_service_name,
    )
    configure_sentry()

    app = FastAPI(
        title="AI Evaluation Engine",
        description=(
            "Production-grade API for evaluating AI model outputs "
            "at enterprise scale. Supports dataset management, "
            "configurable evaluation metrics, asynchronous run "
            "execution, and comprehensive audit logging."
        ),
        version=settings.app_version,
        docs_url="/docs" if settings.is_development else None,
        redoc_url="/redoc" if settings.is_development else None,
        openapi_url=(
            "/openapi.json" if settings.is_development else None
        ),
        lifespan=lifespan,
    )

    # ── Middleware Stack ──────────────────────────────────
    # Order matters: first added = last executed (outermost)

    # CORS (outermost — must run before any other processing)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Request-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
    )

    # Metrics (captures full request lifecycle including auth + rate limiting)
    app.add_middleware(MetricsMiddleware)

    # Correlation ID (sets request_id for all downstream)
    app.add_middleware(CorrelationMiddleware)

    # Rate Limiter (early rejection saves resources)
    app.add_middleware(RateLimiterMiddleware)

    # Audit Logger (logs after auth is available)
    app.add_middleware(AuditMiddleware)

    # ── Exception Handlers ───────────────────────────────
    register_exception_handlers(app)

    # ── Routes ───────────────────────────────────────────
    app.include_router(v1_router)

    # ── Prometheus Metrics ───────────────────────────────
    @app.get("/metrics", include_in_schema=False)
    async def prometheus_metrics() -> Response:
        """Prometheus metrics endpoint for monitoring."""
        try:
            registry = CollectorRegistry()
            multiprocess.MultiProcessCollector(registry)
            data = generate_latest(registry)
        except Exception:
            # Fallback for non-multiprocess mode
            from prometheus_client import REGISTRY

            data = generate_latest(REGISTRY)

        return Response(
            content=data,
            media_type="text/plain; charset=utf-8",
        )

    return app


# Create the app instance for uvicorn
app = create_app()
