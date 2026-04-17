"""
SQLAlchemy models — import all models here to ensure they are registered
with the Base metadata before Alembic or the application creates tables.
"""

from src.models.audit_log import AuditAction, AuditLog
from src.models.base import Base, BaseModel, OptimisticLockMixin
from src.models.claim import Claim
from src.models.contradiction import Contradiction
from src.models.evaluation import (
    EvaluationConfig,
    EvaluationRun,
    RunStatus,
)
from src.models.organization import Organization, PlanTier
from src.models.score import Score
from src.models.submission import Submission, SubmissionStatus
from src.models.user import User, UserRole
from src.models.worker_result import WorkerResult, WorkerStatus

__all__ = [
    "Base",
    "BaseModel",
    "OptimisticLockMixin",
    "Organization",
    "PlanTier",
    "User",
    "UserRole",
    "Submission",
    "SubmissionStatus",
    "EvaluationConfig",
    "EvaluationRun",
    "RunStatus",
    "WorkerResult",
    "WorkerStatus",
    "Claim",
    "Contradiction",
    "Score",
    "AuditLog",
    "AuditAction",
]
