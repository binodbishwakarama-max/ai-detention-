"""
Health check endpoints — Kubernetes-aligned probes.

Provides three levels of health checking:

1. /health/live  — Liveness probe: Is the process running?
   → Always returns 200 if the process can serve requests.
   → Kubernetes uses this for restart decisions.

2. /health/ready — Readiness probe: Is it safe to send traffic?
   → Checks DB + Redis + S3 connectivity (boolean pass/fail).
   → Kubernetes uses this for traffic routing decisions.

3. /health/deps  — Dependency dashboard: Full system status with latency.
   → Per-dependency health with measured latency_ms.
   → Used by monitoring dashboards and incident triage.
"""

from __future__ import annotations

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from src.config import get_settings

import time as time_module

router = APIRouter(tags=["Health"])

# Track process start time for uptime reporting
_BOOT_TIME = time_module.monotonic()


@router.get(
    "/health/live",
    status_code=status.HTTP_200_OK,
    summary="Liveness probe",
    description="Returns 200 if the application process is running.",
)
async def liveness() -> dict:
    """
    Liveness check — the process is alive.

    This endpoint does NO dependency checks. If the process can
    respond to HTTP, it is alive. Kubernetes restarts pods only
    when this endpoint stops responding.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "version": settings.app_version,
        "environment": settings.app_env.value,
    }


@router.get(
    "/health/ready",
    summary="Readiness probe",
    description="Returns 200 if all critical dependencies are available.",
)
async def readiness() -> JSONResponse:
    """
    Readiness check — all critical dependencies must be available.

    Checks PostgreSQL, Redis, and S3. Returns 503 if any are down.
    Kubernetes removes the pod from the load balancer when this fails.
    """
    checks: dict[str, bool] = {}

    # Check PostgreSQL
    checks["postgresql"] = await _check_postgres()

    # Check Redis
    checks["redis"] = await _check_redis()

    # Check S3
    checks["s3"] = await _check_s3()

    all_healthy = all(checks.values())
    settings = get_settings()

    return JSONResponse(
        status_code=(
            status.HTTP_200_OK
            if all_healthy
            else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        content={
            "status": "ok" if all_healthy else "degraded",
            "version": settings.app_version,
            "checks": checks,
        },
    )


@router.get(
    "/health/deps",
    summary="Full dependency status with latency",
    description="Detailed health of every dependency with measured latency.",
)
async def dependency_health() -> JSONResponse:
    """
    Detailed dependency health for monitoring dashboards.

    Each dependency check includes:
    - status: "ok" | "degraded" | "down"
    - latency_ms: milliseconds to complete the health check
    - error: error message if the check failed
    """
    import platform
    import sys

    deps: dict[str, dict] = {}

    # ── PostgreSQL ──────────────────────────────────────
    deps["postgresql"] = await _timed_check("postgresql", _check_postgres)

    # ── Redis ───────────────────────────────────────────
    deps["redis"] = await _timed_check("redis", _check_redis)

    # ── S3 / MinIO ──────────────────────────────────────
    deps["s3"] = await _timed_check("s3", _check_s3)

    # ── Celery Workers ──────────────────────────────────
    deps["celery"] = await _timed_check("celery", _check_celery)

    # Overall status
    statuses = [d["status"] for d in deps.values()]
    if all(s == "ok" for s in statuses):
        overall = "ok"
    elif any(s == "down" for s in statuses):
        overall = "degraded"
    else:
        overall = "degraded"

    settings = get_settings()
    uptime_seconds = round(time_module.monotonic() - _BOOT_TIME, 1)

    return JSONResponse(
        status_code=(
            status.HTTP_200_OK
            if overall == "ok"
            else status.HTTP_503_SERVICE_UNAVAILABLE
        ),
        content={
            "status": overall,
            "uptime_seconds": uptime_seconds,
            "version": settings.app_version,
            "environment": settings.app_env.value,
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "dependencies": deps,
        },
    )


# ── Keep old /health endpoint as alias for backward compat ──────

@router.get(
    "/health",
    status_code=status.HTTP_200_OK,
    summary="Legacy liveness probe (alias for /health/live)",
    include_in_schema=False,
)
async def legacy_health() -> dict:
    """Backward-compatible alias for /health/live."""
    return await liveness()


# ── Private Check Functions ─────────────────────────────────────


async def _timed_check(name: str, check_fn) -> dict:
    """Run a health check and measure its latency."""
    start = time_module.perf_counter()
    try:
        healthy = await check_fn()
        latency_ms = round((time_module.perf_counter() - start) * 1000, 2)
        return {
            "status": "ok" if healthy else "down",
            "latency_ms": latency_ms,
        }
    except Exception as e:
        latency_ms = round((time_module.perf_counter() - start) * 1000, 2)
        return {
            "status": "down",
            "latency_ms": latency_ms,
            "error": str(e),
        }


async def _check_postgres() -> bool:
    """Check PostgreSQL connectivity with a simple query."""
    try:
        from sqlalchemy import text

        from src.database import get_engine

        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _check_redis() -> bool:
    """Check Redis connectivity with PING."""
    from src.redis_client import redis_health_check
    return await redis_health_check()


async def _check_s3() -> bool:
    """Check S3/MinIO connectivity with a HEAD bucket call."""
    try:
        from src.s3_client import get_s3_client

        client = get_s3_client()
        settings = get_settings()
        client.head_bucket(Bucket=settings.s3_bucket_name)
        return True
    except Exception:
        return False


async def _check_celery() -> bool:
    """Check if any Celery workers are responding."""
    try:
        import asyncio

        from src.workers.celery_app import celery_app

        # Run the blocking inspect in a thread to not block the event loop
        result = await asyncio.to_thread(
            lambda: celery_app.control.inspect().ping()
        )
        return result is not None and len(result) > 0
    except Exception:
        return False
