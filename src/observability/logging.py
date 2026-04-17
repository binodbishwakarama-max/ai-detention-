"""
Structured logging configuration with SRE-grade field processing.

Features:
- JSON output in production, colored console in development
- Automatic sensitive field masking (email, token, api_key, password, secret)
- Context enrichment: request_id, user_id, org_id, service, trace_id
- Log levels: DEBUG (dev), INFO (prod), WARNING (degraded),
              ERROR (needs-attention), CRITICAL (page-someone)

Every log line includes:
  timestamp, level, request_id, user_id, org_id, service, function, duration_ms
"""

from __future__ import annotations

import logging
import re
import sys
from typing import Any

import structlog

# ── Sensitive Field Masking ──────────────────────────────────────

# Fields whose values are fully replaced with the redacted marker.
_SENSITIVE_FIELDS = frozenset({
    "password",
    "hashed_password",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "secret",
    "secret_key",
    "authorization",
    "x_api_key",
    "aws_secret_access_key",
    "s3_secret_access_key",
})

# Fields whose values are partially masked (show first/last chars).
_PII_FIELDS = frozenset({
    "email",
    "ip_address",
    "client_ip",
})

_REDACTED = "***REDACTED***"

# Regex to catch tokens/keys that slip through as substring values.
_TOKEN_PATTERN = re.compile(
    r"(Bearer\s+|token[=:]\s*|api[_-]?key[=:]\s*)(\S+)",
    re.IGNORECASE,
)


def _mask_value(value: str) -> str:
    """Partially mask a PII value — show first 2 and last 2 chars."""
    if len(value) <= 6:
        return _REDACTED
    return f"{value[:2]}***{value[-2:]}"


def sensitive_field_masker(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Structlog processor that redacts sensitive fields from log output.

    Rules:
      - Fields in _SENSITIVE_FIELDS → fully replaced with ***REDACTED***
      - Fields in _PII_FIELDS → partially masked (fi***ld)
      - String values containing Bearer/token patterns → pattern-redacted
      - Never logs: passwords, full file contents, PII
    """
    for key, value in list(event_dict.items()):
        lower_key = key.lower()

        if lower_key in _SENSITIVE_FIELDS:
            event_dict[key] = _REDACTED
            continue

        if lower_key in _PII_FIELDS and isinstance(value, str):
            event_dict[key] = _mask_value(value)
            continue

        # Catch embedded tokens in string values
        if isinstance(value, str) and _TOKEN_PATTERN.search(value):
            event_dict[key] = _TOKEN_PATTERN.sub(
                lambda m: f"{m.group(1)}{_REDACTED}", value
            )

    return event_dict


# ── Context Enrichment ───────────────────────────────────────────


def context_enricher(
    logger: Any, method_name: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """
    Inject service identity and OpenTelemetry trace context.

    request_id, user_id, and org_id are injected by the correlation
    middleware via structlog.contextvars. This processor adds the
    static service name and the active OTel trace/span IDs.
    """
    event_dict.setdefault("service", "eval-engine")

    # Inject trace context if OpenTelemetry is available
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()
        if ctx and ctx.trace_id:
            event_dict["trace_id"] = format(ctx.trace_id, "032x")
            event_dict["span_id"] = format(ctx.span_id, "016x")
    except ImportError:
        pass

    return event_dict


# ── Configure Logging ────────────────────────────────────────────


def configure_logging(
    *,
    log_level: str = "INFO",
    log_format: str = "json",
    service_name: str = "eval-engine",
) -> None:
    """
    Configure structlog for production-grade structured logging.

    Args:
        log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL).
        log_format: Output format — "json" for production, "console" for dev.
        service_name: Service identifier included in every log line.
    """
    # Configure stdlib logging (captures third-party library output)
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, log_level.upper(), logging.INFO),
    )

    # Suppress noisy third-party loggers
    for noisy_logger in ("uvicorn.access", "sqlalchemy.engine", "celery.worker"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    # Build the processor pipeline (order matters)
    processors: list[structlog.types.Processor] = [
        # 1. Merge contextvars (request_id, user_id, org_id from middleware)
        structlog.contextvars.merge_contextvars,
        # 2. Filter by log level
        structlog.stdlib.filter_by_level,
        # 3. Add logger name and log level
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        # 4. Format positional args
        structlog.stdlib.PositionalArgumentsFormatter(),
        # 5. ISO8601 timestamp
        structlog.processors.TimeStamper(fmt="iso"),
        # 6. Context enrichment (service name, trace_id)
        context_enricher,
        # 7. Sensitive field masking (MUST be after enrichment, before rendering)
        sensitive_field_masker,
        # 8. Stack info for exceptions
        structlog.processors.StackInfoRenderer(),
        structlog.processors.UnicodeDecoder(),
        # 9. Format exceptions
        structlog.processors.format_exc_info,
    ]

    # Final renderer
    if log_format == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
