"""
Webhook delivery service.

Delivers evaluation completion notifications to client-registered URLs.
Implements retry with exponential backoff for resilient delivery:
- 3 retry attempts
- Exponential backoff: 1s, 2s, 4s
- Dead letter logging for permanently failed deliveries

Security:
- HMAC-SHA256 signature in X-Webhook-Signature header
- Timestamp in X-Webhook-Timestamp for replay protection
- 10-second timeout per delivery attempt
"""

from __future__ import annotations

import hashlib
import hmac
import time
from typing import Any
from uuid import UUID

import httpx
import orjson
import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.config import get_settings

logger = structlog.get_logger(__name__)


def _sign_payload(payload: bytes, secret: str) -> str:
    """
    Create HMAC-SHA256 signature for webhook payload.

    Clients verify this signature to ensure the webhook came from us
    and hasn't been tampered with in transit.
    """
    return hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(
        (
            httpx.HTTPStatusError,
            httpx.ConnectError,
            httpx.TimeoutException,
        )
    ),
    reraise=True,
)
async def _deliver_with_retry(
    url: str,
    payload: bytes,
    headers: dict[str, str],
) -> int:
    """
    Deliver webhook with retry logic.

    Returns the HTTP status code on success.
    Retries on 5xx errors, connection errors, and timeouts.
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            url, content=payload, headers=headers
        )
        # Only retry on server errors, not client errors
        if response.status_code >= 500:
            response.raise_for_status()
        return response.status_code


async def deliver_webhook(
    url: str,
    event_type: str,
    payload: dict[str, Any],
    org_id: UUID | None = None,
) -> bool:
    """
    Deliver a webhook notification to the registered URL.

    Args:
        url: The webhook endpoint URL
        event_type: Event type identifier (e.g., 'evaluation.completed')
        payload: The event data
        org_id: Organization ID for logging context

    Returns:
        True if delivery succeeded, False if all retries failed
    """
    settings = get_settings()
    timestamp = str(int(time.time()))

    body = orjson.dumps(
        {
            "event": event_type,
            "timestamp": timestamp,
            "data": payload,
        }
    )

    signature = _sign_payload(body, settings.secret_key)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Signature": f"sha256={signature}",
        "X-Webhook-Timestamp": timestamp,
        "X-Webhook-Event": event_type,
        "User-Agent": f"EvalEngine/{settings.app_version}",
    }

    try:
        status_code = await _deliver_with_retry(url, body, headers)
        logger.info(
            "webhook.delivered",
            url=url,
            event=event_type,
            status_code=status_code,
            org_id=str(org_id) if org_id else None,
        )
        return True
    except Exception:
        # Dead letter: log the failed delivery for manual investigation
        logger.error(
            "webhook.delivery_failed",
            url=url,
            event=event_type,
            org_id=str(org_id) if org_id else None,
            payload_size=len(body),
        )
        return False
