"""Pydantic schemas for request/response validation."""

from src.schemas.auth import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyResponse,
    TokenRefresh,
    TokenResponse,
    UserCreate,
    UserLogin,
    UserResponse,
    UserUpdate,
)
from src.schemas.common import (
    BaseSchema,
    ErrorResponse,
    HealthResponse,
    MessageResponse,
    PaginatedResponse,
    PaginationParams,
)
from src.schemas.dataset import (
    DatasetConfirmUpload,
    DatasetCreate,
    DatasetCreateResponse,
    DatasetResponse,
    DatasetUpdate,
)
from src.schemas.evaluation import (
    EvaluationConfigCreate,
    EvaluationConfigResponse,
    EvaluationConfigUpdate,
    EvaluationRunResponse,
)
from src.schemas.metric import MetricCreate, MetricResponse, MetricUpdate
from src.schemas.result import (
    ClaimResponse,
    ContradictionResponse,
    ResultExportRequest,
    ResultExportResponse,
    RunResultsSummary,
    ScoreResponse,
    WorkerResultResponse,
)
from src.schemas.submission import (
    SubmissionCreate,
    SubmissionEvaluate,
    SubmissionResponse,
    SubmissionUpdate,
)

__all__ = [
    "BaseSchema",
    "ErrorResponse",
    "HealthResponse",
    "MessageResponse",
    "PaginatedResponse",
    "PaginationParams",
    "UserCreate",
    "UserLogin",
    "UserResponse",
    "UserUpdate",
    "TokenResponse",
    "TokenRefresh",
    "ApiKeyCreate",
    "ApiKeyCreated",
    "ApiKeyResponse",
    "EvaluationConfigCreate",
    "EvaluationConfigResponse",
    "EvaluationConfigUpdate",
    "EvaluationRunResponse",
    "DatasetCreate",
    "DatasetCreateResponse",
    "DatasetConfirmUpload",
    "DatasetResponse",
    "DatasetUpdate",
    "MetricCreate",
    "MetricResponse",
    "MetricUpdate",
    "WorkerResultResponse",
    "ClaimResponse",
    "ContradictionResponse",
    "ScoreResponse",
    "RunResultsSummary",
    "ResultExportRequest",
    "ResultExportResponse",
    "SubmissionCreate",
    "SubmissionUpdate",
    "SubmissionEvaluate",
    "SubmissionResponse",
]
