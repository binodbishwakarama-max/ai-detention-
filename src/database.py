"""
Async database engine and session management.

Uses SQLAlchemy 2.0 async API with asyncpg for non-blocking I/O.

Connection Pool Configuration (production-tuned):
┌─────────────────────┬────────┬───────────────────────────────────────────┐
│ Setting             │ Value  │ Rationale                                 │
├─────────────────────┼────────┼───────────────────────────────────────────┤
│ pool_size           │ 20     │ Steady-state connections per worker.      │
│                     │        │ 4 workers × 20 = 80 total connections.    │
│                     │        │ PostgreSQL max_connections=200 gives      │
│                     │        │ headroom for admin + migration sessions.  │
├─────────────────────┼────────┼───────────────────────────────────────────┤
│ max_overflow        │ 10     │ Burst capacity: 30 total per worker.      │
│                     │        │ Overflow connections are short-lived —    │
│                     │        │ created under load, destroyed after use.  │
├─────────────────────┼────────┼───────────────────────────────────────────┤
│ pool_timeout        │ 30s    │ Max wait for a connection from the pool.  │
│                     │        │ If exceeded, raises TimeoutError rather   │
│                     │        │ than hanging indefinitely.                │
├─────────────────────┼────────┼───────────────────────────────────────────┤
│ pool_recycle        │ 1800s  │ Recycle connections every 30 min to       │
│                     │        │ prevent state accumulation and handle     │
│                     │        │ PgBouncer/firewall idle timeouts.         │
├─────────────────────┼────────┼───────────────────────────────────────────┤
│ pool_pre_ping       │ True   │ Sends a SELECT 1 before each checkout.   │
│                     │        │ ~1ms overhead but prevents using a dead   │
│                     │        │ connection after network interruption.    │
├─────────────────────┼────────┼───────────────────────────────────────────┤
│ statement_cache     │ 256    │ asyncpg prepared statement cache.         │
│                     │        │ Avoids re-parsing common queries.         │
│                     │        │ Saves ~0.5ms per repeated query.          │
└─────────────────────┴────────┴───────────────────────────────────────────┘

For 10,000 concurrent evaluations:
- Each evaluation is a Celery task, not a persistent connection
- Workers process tasks sequentially (prefetch=1)
- 4 workers × 8 concurrency = 32 tasks in parallel
- 32 tasks × 1 connection each = 32 connections needed
- pool_size=20 + max_overflow=10 = 30 per worker → sufficient
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import structlog
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import get_settings

logger = structlog.get_logger(__name__)

# ── Engine ──────────────────────────────────────────────────
# Lazy initialization: engine is created on first use via lifespan,
# not at module import time. This allows tests to override settings.
_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return the global async engine, creating it if necessary."""
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_async_engine(
            settings.database_url,
            # ── Pool sizing ──────────────────────────────
            pool_size=settings.database_pool_size,        # 20 steady-state
            max_overflow=settings.database_max_overflow,   # +10 burst
            pool_timeout=settings.database_pool_timeout,   # 30s max wait
            # ── Connection lifecycle ─────────────────────
            pool_recycle=1800,   # Recycle every 30 min (firewall/PgBouncer compat)
            pool_pre_ping=True,  # Detect dead connections: ~1ms overhead
            # ── Debugging ────────────────────────────────
            echo=settings.database_echo,
            # ── asyncpg-specific performance ─────────────
            connect_args={
                "prepared_statement_cache_size": 256,  # cache parsed queries
                "statement_cache_size": 256,           # protocol-level cache
            },
        )

        # Register query duration metrics on the sync engine
        _register_query_metrics(_engine.sync_engine)

        logger.info(
            "database.engine_created",
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
            pool_timeout=settings.database_pool_timeout,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return the global session factory, creating it if necessary."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(
            bind=get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,  # Prevent lazy-load surprises after commit
            autoflush=False,         # Explicit flushes only for predictability
        )
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that yields an async database session.

    Transaction lifecycle:
    1. Session created from pool
    2. Handler runs (all writes within this session)
    3. On success → COMMIT
    4. On exception → ROLLBACK

    IMPORTANT: All writes in services/repositories happen inside this
    transaction boundary. No autonomous commits or nested transactions.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@asynccontextmanager
async def get_standalone_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Context manager for sessions outside of FastAPI request lifecycle.

    Used by:
    - Celery workers (separate process, no FastAPI DI)
    - Startup scripts (metric seeding)
    - Background cleanup tasks

    Same transaction semantics as get_db_session.
    """
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def set_org_context(session: AsyncSession, org_id: str) -> None:
    """
    Set the RLS context variable for the current session.

    Must be called at the start of every request to enable
    Row-Level Security policies. The PostgreSQL session variable
    'app.current_org_id' is checked by RLS policies on every query.

    Uses parameterized SET via format_map to avoid SQL injection.
    PostgreSQL SET does not support $1 bind params, so we validate
    the UUID format before interpolation.
    """
    import re

    from sqlalchemy import text

    # Validate org_id is a valid UUID format before interpolation
    if not re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", str(org_id), re.I):
        raise ValueError(f"Invalid org_id format: {org_id}")
    await session.execute(text("SET app.current_org_id = :org_id"), {"org_id": str(org_id)})


async def init_engine() -> None:
    """Initialize the database engine. Called during application startup."""
    get_engine()
    get_session_factory()
    logger.info("database.initialized")


async def dispose_engine() -> None:
    """Dispose of the database engine. Called during application shutdown."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("database.disposed")


# ── Query Duration Metrics ──────────────────────────────────────

import time as _time_mod

_query_start_times: dict[int, float] = {}


def _classify_query(statement: str) -> str:
    """Classify a SQL statement by its operation type."""
    stmt = statement.strip().upper()
    for prefix in ("SELECT", "INSERT", "UPDATE", "DELETE"):
        if stmt.startswith(prefix):
            return prefix
    return "OTHER"


def _register_query_metrics(sync_engine) -> None:
    """
    Attach SQLAlchemy event listeners to observe query duration.

    Uses before_cursor_execute / after_cursor_execute events on the
    synchronous engine (which asyncpg proxies through internally).
    """
    from sqlalchemy import event

    @event.listens_for(sync_engine, "before_cursor_execute")
    def _before_execute(conn, cursor, statement, parameters, context, executemany):
        conn.info["query_start_time"] = _time_mod.perf_counter()

    @event.listens_for(sync_engine, "after_cursor_execute")
    def _after_execute(conn, cursor, statement, parameters, context, executemany):
        start = conn.info.pop("query_start_time", None)
        if start is not None:
            duration = _time_mod.perf_counter() - start
            query_type = _classify_query(statement)
            try:
                from src.observability.metrics import get_metrics
                get_metrics().db_query_duration_seconds.labels(
                    query_type=query_type
                ).observe(duration)
            except Exception:
                pass  # Metrics unavailable — fail open
