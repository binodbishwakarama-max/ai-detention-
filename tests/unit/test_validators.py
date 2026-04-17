"""Unit tests for input validators."""

from __future__ import annotations

import pytest

from src.utils.validators import (
    is_valid_scope,
    is_valid_slug,
    is_valid_uuid,
    sanitize_string,
    validate_webhook_url,
)


class TestIsValidUUID:
    def test_valid_uuid4(self):
        assert is_valid_uuid("550e8400-e29b-41d4-a716-446655440000") is True

    def test_invalid_uuid(self):
        assert is_valid_uuid("not-a-uuid") is False

    def test_empty_string(self):
        assert is_valid_uuid("") is False


class TestIsValidSlug:
    def test_valid_slug(self):
        assert is_valid_slug("my-org") is True
        assert is_valid_slug("a") is True
        assert is_valid_slug("test123") is True

    def test_invalid_slug_uppercase(self):
        assert is_valid_slug("My-Org") is False

    def test_invalid_slug_consecutive_hyphens(self):
        assert is_valid_slug("my--org") is False

    def test_invalid_slug_starts_with_hyphen(self):
        assert is_valid_slug("-my-org") is False

    def test_slug_too_long(self):
        assert is_valid_slug("a" * 64) is False

    def test_empty_slug(self):
        assert is_valid_slug("") is False


class TestIsValidScope:
    def test_valid_scope(self):
        assert is_valid_scope("evaluations:read") is True
        assert is_valid_scope("admin:manage") is True

    def test_invalid_scope_no_colon(self):
        assert is_valid_scope("evaluations") is False

    def test_invalid_scope_uppercase(self):
        assert is_valid_scope("Evaluations:Read") is False


class TestSanitizeString:
    def test_strip_whitespace(self):
        assert sanitize_string("  hello  ") == "hello"

    def test_collapse_spaces(self):
        assert sanitize_string("hello   world") == "hello world"

    def test_remove_null_bytes(self):
        assert sanitize_string("hello\x00world") == "helloworld"

    def test_truncate_to_max_length(self):
        result = sanitize_string("a" * 500, max_length=10)
        assert len(result) == 10


class TestValidateWebhookUrl:
    def test_valid_https(self):
        assert validate_webhook_url("https://api.example.com/webhook") is True

    def test_localhost_http_allowed(self):
        assert validate_webhook_url("http://localhost:8080/hook") is True

    def test_plain_http_rejected(self):
        assert validate_webhook_url("http://external.com/hook") is False

    def test_internal_ip_blocked(self):
        """SSRF prevention — block private IP ranges."""
        assert validate_webhook_url("https://10.0.0.1/hook") is False
        assert validate_webhook_url("https://192.168.1.1/hook") is False
        assert validate_webhook_url("https://172.16.0.1/hook") is False
        assert validate_webhook_url("https://169.254.1.1/hook") is False

    def test_invalid_url_rejected(self):
        assert validate_webhook_url("not-a-url") is False
        assert validate_webhook_url("") is False
