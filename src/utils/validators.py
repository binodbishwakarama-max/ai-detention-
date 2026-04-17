"""
Input validation utilities.

Provides reusable validators for common patterns used across
the API layer. These complement Pydantic's built-in validation
with domain-specific rules.
"""

from __future__ import annotations

import re
from uuid import UUID


def is_valid_uuid(value: str) -> bool:
    """Check if a string is a valid UUID."""
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False


def is_valid_slug(value: str) -> bool:
    """
    Validate a URL-safe slug.

    Rules:
    - 1-63 characters
    - Lowercase alphanumeric and hyphens only
    - Cannot start or end with a hyphen
    - No consecutive hyphens
    """
    if not value or len(value) > 63:
        return False
    pattern = r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$"
    if not re.match(pattern, value):
        return False
    if "--" in value:
        return False
    return True


def is_valid_scope(scope: str) -> bool:
    """
    Validate an API key scope string.

    Valid formats: "resource:action" where both parts are lowercase alpha.
    Examples: "evaluations:read", "datasets:write", "admin:manage"
    """
    pattern = r"^[a-z_]+:[a-z_]+$"
    return bool(re.match(pattern, scope))


def sanitize_string(value: str, max_length: int = 255) -> str:
    """
    Sanitize a user-provided string.

    - Strip leading/trailing whitespace
    - Collapse multiple spaces
    - Truncate to max_length
    - Remove null bytes (security: prevents null byte injection)
    """
    value = value.strip()
    value = re.sub(r"\s+", " ", value)
    value = value.replace("\x00", "")
    return value[:max_length]


def validate_webhook_url(url: str) -> bool:
    """
    Validate a webhook URL.

    Rules:
    - Must use HTTPS (except localhost for development)
    - Must be a valid URL format
    - Cannot be an IP address (prevents SSRF to internal services)
    """
    import urllib.parse

    try:
        parsed = urllib.parse.urlparse(url)
    except Exception:
        return False

    # Must have scheme and netloc
    if not parsed.scheme or not parsed.netloc:
        return False

    # HTTPS required (except localhost for development)
    if parsed.scheme != "https":
        if parsed.hostname not in ("localhost", "127.0.0.1"):
            return False

    # Block common internal IP ranges (basic SSRF prevention)
    hostname = parsed.hostname or ""
    blocked_prefixes = (
        "10.",
        "172.16.",
        "172.17.",
        "172.18.",
        "172.19.",
        "172.20.",
        "172.21.",
        "172.22.",
        "172.23.",
        "172.24.",
        "172.25.",
        "172.26.",
        "172.27.",
        "172.28.",
        "172.29.",
        "172.30.",
        "172.31.",
        "192.168.",
        "169.254.",
    )
    if any(hostname.startswith(prefix) for prefix in blocked_prefixes):
        return False

    return True
