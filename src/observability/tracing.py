"""
OpenTelemetry distributed tracing setup.

Provides end-to-end request tracing across:
  FastAPI → SQLAlchemy → Redis → httpx → Celery workers

Exporters:
  - Development: Jaeger (OTLP/gRPC on localhost:4317)
  - Production:  OTLP exporter (Google Cloud Trace or any OTLP backend)
  - Debug:       Console exporter (prints spans to stdout)

Celery integration:
  - inject_trace_context(): Serialize active span into Celery task headers
  - extract_trace_context(): Restore span context inside a Celery worker
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)

_tracer_provider = None


def init_tracing(
    *,
    service_name: str = "eval-engine",
    exporter_type: str = "jaeger",
    endpoint: str = "http://localhost:4317",
    sample_rate: float = 1.0,
    enabled: bool = True,
    app: "FastAPI" | None = None,
) -> None:
    """
    Initialize the OpenTelemetry tracing pipeline.

    Args:
        service_name: Logical service name for span identification.
        exporter_type: "jaeger" | "otlp" | "console".
        endpoint: OTLP gRPC endpoint (used by jaeger and otlp exporters).
        sample_rate: Fraction of traces to sample (1.0 = all, 0.1 = 10%).
        enabled: Set False to completely disable tracing (zero overhead).
        app: Optional FastAPI application instance to instrument.
    """
    global _tracer_provider

    if not enabled:
        logger.info("tracing.disabled")
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

        resource = Resource.create({
            "service.name": service_name,
            "service.version": "1.0.0",
            "deployment.environment": "production",
        })

        sampler = TraceIdRatioBased(sample_rate)
        _tracer_provider = TracerProvider(resource=resource, sampler=sampler)

        # Configure exporter
        if exporter_type == "console":
            from opentelemetry.sdk.trace.export import (
                SimpleSpanProcessor,
                ConsoleSpanExporter,
            )
            _tracer_provider.add_span_processor(
                SimpleSpanProcessor(ConsoleSpanExporter())
            )
        else:
            # Both "jaeger" and "otlp" use the OTLP gRPC exporter
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.trace.export import BatchSpanProcessor

            otlp_exporter = OTLPSpanExporter(
                endpoint=endpoint,
                insecure=True,
            )
            _tracer_provider.add_span_processor(
                BatchSpanProcessor(
                    otlp_exporter,
                    max_queue_size=2048,
                    max_export_batch_size=512,
                    schedule_delay_millis=5000,
                )
            )

        trace.set_tracer_provider(_tracer_provider)

        # ── Auto-Instrumentation ─────────────────────────────
        _instrument_libraries(app)

        logger.info(
            "tracing.initialized",
            exporter=exporter_type,
            endpoint=endpoint,
            sample_rate=sample_rate,
        )

    except ImportError as e:
        logger.warning(
            "tracing.import_error",
            error=str(e),
            hint="Install opentelemetry-sdk and exporters",
        )
    except Exception as e:
        logger.error("tracing.init_failed", error=str(e))


def _instrument_libraries(app: "FastAPI" | None = None) -> None:
    """Auto-instrument supported libraries with OpenTelemetry."""

    # FastAPI / Starlette
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        if app:
            FastAPIInstrumentor().instrument_app(app)
            logger.debug("tracing.instrumented", library="fastapi", mode="app")
        else:
            # Global instrumentation for all instances if app not available yet
            FastAPIInstrumentor().instrument()
            logger.debug("tracing.instrumented", library="fastapi", mode="global")
    except ImportError:
        pass
    except Exception as e:
        logger.error("tracing.instrumentation_failed", library="fastapi", error=str(e))

    # SQLAlchemy
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        SQLAlchemyInstrumentor().instrument()
        logger.debug("tracing.instrumented", library="sqlalchemy")
    except ImportError:
        pass

    # Redis
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        RedisInstrumentor().instrument()
        logger.debug("tracing.instrumented", library="redis")
    except ImportError:
        pass

    # httpx (for outbound HTTP calls to LLM APIs, webhooks)
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
        HTTPXClientInstrumentor().instrument()
        logger.debug("tracing.instrumented", library="httpx")
    except ImportError:
        pass

    # Celery
    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        CeleryInstrumentor().instrument()
        logger.debug("tracing.instrumented", library="celery")
    except ImportError:
        pass


def get_tracer(name: str = __name__):
    """
    Get a named tracer for creating manual spans.

    Usage:
        tracer = get_tracer(__name__)
        with tracer.start_as_current_span("my_operation") as span:
            span.set_attribute("key", "value")
            ...
    """
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        return _NoOpTracer()


# ── Celery Trace Propagation ────────────────────────────────────


def inject_trace_context() -> dict[str, str]:
    """
    Serialize the current trace context into a dict for Celery task headers.

    Call this at task dispatch time:
        headers = inject_trace_context()
        my_task.apply_async(args=[...], headers=headers)
    """
    try:
        from opentelemetry import context
        from opentelemetry.propagators import textmap
        from opentelemetry.propagate import inject

        carrier: dict[str, str] = {}
        inject(carrier)
        return carrier
    except ImportError:
        return {}


def extract_trace_context(headers: dict[str, str] | None = None):
    """
    Restore trace context from Celery task headers inside a worker.

    Call this at task execution time:
        ctx = extract_trace_context(self.request.get("headers", {}))
    """
    if not headers:
        return None
    try:
        from opentelemetry.propagate import extract
        return extract(headers)
    except ImportError:
        return None


async def shutdown_tracing() -> None:
    """Flush pending spans and shut down the tracer provider."""
    global _tracer_provider
    if _tracer_provider is not None:
        _tracer_provider.shutdown()
        _tracer_provider = None
        logger.info("tracing.shutdown")


# ── No-Op Fallback ──────────────────────────────────────────────


class _NoOpSpan:
    """Fallback span when OTel is not installed."""
    def set_attribute(self, key: str, value) -> None: ...
    def set_status(self, status) -> None: ...
    def record_exception(self, exc: Exception) -> None: ...
    def __enter__(self): return self
    def __exit__(self, *args): ...


class _NoOpTracer:
    """Fallback tracer when OTel is not installed."""
    def start_as_current_span(self, name: str, **kwargs):
        return _NoOpSpan()
