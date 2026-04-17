"""Unit tests for observability modules."""

from __future__ import annotations

import pytest

from src.observability.logging import (
    _REDACTED,
    _mask_value,
    sensitive_field_masker,
)
from src.observability.metrics import MetricsRegistry, get_metrics


class TestSensitiveFieldMasker:
    def _process(self, event_dict: dict) -> dict:
        return sensitive_field_masker(None, "info", event_dict)

    def test_password_fully_redacted(self):
        result = self._process({"password": "secret123"})
        assert result["password"] == _REDACTED

    def test_token_fully_redacted(self):
        result = self._process({"token": "abc123"})
        assert result["token"] == _REDACTED

    def test_api_key_fully_redacted(self):
        result = self._process({"api_key": "sk-12345"})
        assert result["api_key"] == _REDACTED

    def test_authorization_fully_redacted(self):
        result = self._process({"authorization": "Bearer xyz"})
        assert result["authorization"] == _REDACTED

    def test_email_partially_masked(self):
        result = self._process({"email": "user@test.com"})
        assert result["email"].startswith("us")
        assert result["email"].endswith("om")
        assert "***" in result["email"]

    def test_short_email_fully_redacted(self):
        result = self._process({"email": "a@b.c"})
        assert result["email"] == _REDACTED

    def test_bearer_token_in_value_redacted(self):
        result = self._process({
            "header": "Bearer eyJhbGciOi.payload.sig"
        })
        assert "eyJhbGciOi" not in result["header"]
        assert _REDACTED in result["header"]

    def test_non_sensitive_fields_untouched(self):
        result = self._process({
            "user_id": "abc-123",
            "status": "ok",
        })
        assert result["user_id"] == "abc-123"
        assert result["status"] == "ok"

    def test_secret_key_redacted(self):
        result = self._process({"secret_key": "my-secret"})
        assert result["secret_key"] == _REDACTED

    def test_hashed_password_redacted(self):
        result = self._process({"hashed_password": "$2b$12$..."})
        assert result["hashed_password"] == _REDACTED


class TestMaskValue:
    def test_long_value_partially_masked(self):
        result = _mask_value("user@example.com")
        assert result == "us***.om"

    def test_short_value_fully_redacted(self):
        result = _mask_value("short")
        assert result == _REDACTED


class TestMetricsRegistry:
    def test_singleton(self):
        m1 = get_metrics()
        m2 = get_metrics()
        assert m1 is m2

    def test_http_counter_increments(self):
        metrics = MetricsRegistry()
        metrics.http_requests_total.labels(
            method="GET", endpoint="/test", status_code="200"
        ).inc()
        # Counter should not raise

    def test_histogram_observes(self):
        metrics = MetricsRegistry()
        metrics.http_request_duration_seconds.labels(
            method="GET", endpoint="/test"
        ).observe(0.1)
        # Histogram should not raise

    def test_gauge_sets(self):
        metrics = MetricsRegistry()
        metrics.active_evaluations_gauge.set(5)
        # Gauge should not raise

    def test_all_metrics_exist(self):
        metrics = MetricsRegistry()
        # HTTP
        assert metrics.http_requests_total is not None
        assert metrics.http_request_duration_seconds is not None
        assert metrics.http_requests_in_progress is not None
        # Celery
        assert metrics.celery_task_duration_seconds is not None
        assert metrics.celery_tasks_total is not None
        assert metrics.celery_queue_depth is not None
        # LLM
        assert metrics.llm_tokens_used_total is not None
        assert metrics.llm_cost_usd_total is not None
        # Cache
        assert metrics.cache_hits_total is not None
        assert metrics.cache_misses_total is not None
        # DB
        assert metrics.db_query_duration_seconds is not None
        # Business
        assert metrics.active_evaluations_gauge is not None
