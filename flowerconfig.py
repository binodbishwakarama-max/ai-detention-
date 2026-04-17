"""
Flower configuration — Celery monitoring dashboard.

Flower provides:
- Real-time task monitoring (active, processed, failed)
- Worker status and resource usage
- Task result inspection
- Rate limiting and task control

Access: http://localhost:5555
Auth: Basic auth required (FLOWER_USER / FLOWER_PASSWORD env vars)
"""

from __future__ import annotations

import os

# ── Authentication ───────────────────────────────────────────
# Flower uses HTTP Basic Auth. Credentials from environment variables.
basic_auth = [
    f"{os.getenv('FLOWER_USER', 'admin')}:{os.getenv('FLOWER_PASSWORD', 'flower_secret')}"
]

# ── Server ───────────────────────────────────────────────────
address = "0.0.0.0"
port = 5555

# ── Persistence ──────────────────────────────────────────────
# Persist task data across restarts
persistent = True
db = "/data/flower.db"

# ── Task Settings ────────────────────────────────────────────
# How long to keep task results in the dashboard
max_tasks = 10000

# Natural sort tasks by time received
natural_time = True

# ── Broker ───────────────────────────────────────────────────
# Auto-detect from Celery config
broker_api = os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1")

# ── Refresh ──────────────────────────────────────────────────
# Dashboard auto-refresh interval (milliseconds)
auto_refresh = True
