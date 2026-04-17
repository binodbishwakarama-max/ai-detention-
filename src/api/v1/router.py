"""
API v1 router — aggregates all v1 endpoint routers.
"""

from __future__ import annotations

from fastapi import APIRouter

from src.api.v1.auth import router as auth_router
from src.api.v1.datasets import router as datasets_router
from src.api.v1.evaluations import router as evaluations_router
from src.api.v1.health import router as health_router
from src.api.v1.metrics import router as metrics_router
from src.api.v1.results import router as results_router
from src.api.v1.submissions import router as submissions_router
from src.api.v1.ws_runs import router as ws_runs_router

# Create the v1 router with /api/v1 prefix
v1_router = APIRouter(prefix="/api/v1")

# Include all sub-routers
v1_router.include_router(health_router)
v1_router.include_router(auth_router)
v1_router.include_router(submissions_router)
v1_router.include_router(evaluations_router)
v1_router.include_router(datasets_router)
v1_router.include_router(metrics_router)
v1_router.include_router(results_router)
v1_router.include_router(ws_runs_router)
