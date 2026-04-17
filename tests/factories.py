"""
Factory definitions for all domain models.

Uses factory_boy with SQLAlchemy async support for deterministic test data.
All factories produce valid, fully-formed objects with sensible defaults.

Usage:
    org = await OrganizationFactory.create(session=db)
    user = await UserFactory.create(session=db, organization=org)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from src.models.api_key import ApiKey
from src.models.audit_log import AuditAction, AuditLog
from src.models.dataset import Dataset, DatasetStatus
from src.models.evaluation import (
    EvaluationConfig,
    EvaluationRun,
    RunStatus,
)
from src.models.metric import Metric, MetricType
from src.models.organization import Organization, PlanTier
from src.models.user import User
from src.security import Role, hash_password


# ── Helpers ──────────────────────────────────────────────────

_counter = 0


def _next_id() -> int:
    global _counter
    _counter += 1
    return _counter


def _uuid() -> uuid.UUID:
    """Generate a deterministic UUID for testing."""
    return uuid.uuid4()


# ── Factory Functions ────────────────────────────────────────
# Using simple async factory functions instead of factory_boy
# because factory_boy's async support is fragile with SQLAlchemy 2.0.


async def create_organization(
    db,
    *,
    name: str | None = None,
    slug: str | None = None,
    plan_tier: PlanTier = PlanTier.PRO,
    **overrides,
) -> Organization:
    """Create a test organization."""
    n = _next_id()
    org = Organization(
        name=name or f"Test Org {n}",
        slug=slug or f"test-org-{n}",
        plan_tier=plan_tier,
        **overrides,
    )
    db.add(org)
    await db.flush()
    return org


async def create_user(
    db,
    *,
    organization: Organization | None = None,
    email: str | None = None,
    password: str = "TestPass123!",
    full_name: str | None = None,
    role: Role = Role.ADMIN,
    **overrides,
) -> User:
    """Create a test user. Creates an org if none provided."""
    n = _next_id()
    if organization is None:
        organization = await create_organization(db)

    user = User(
        email=email or f"user{n}@test.com",
        hashed_password=hash_password(password),
        full_name=full_name or f"Test User {n}",
        role=role,
        organization_id=organization.id,
        **overrides,
    )
    db.add(user)
    await db.flush()
    return user


async def create_dataset(
    db,
    *,
    organization: Organization | None = None,
    user: User | None = None,
    name: str | None = None,
    status: DatasetStatus = DatasetStatus.READY,
    sample_count: int = 100,
    **overrides,
) -> Dataset:
    """Create a test dataset."""
    n = _next_id()
    if organization is None:
        organization = await create_organization(db)
    if user is None:
        user = await create_user(db, organization=organization)

    dataset = Dataset(
        name=name or f"Test Dataset {n}",
        organization_id=organization.id,
        created_by_id=user.id,
        storage_path=f"datasets/{organization.id}/{_uuid()}/data.json",
        size_bytes=1024 * n,
        checksum=f"sha256-{uuid.uuid4().hex[:16]}",
        status=status,
        sample_count=sample_count,
        metadata_={},
        **overrides,
    )
    db.add(dataset)
    await db.flush()
    return dataset


async def create_evaluation_config(
    db,
    *,
    organization: Organization | None = None,
    user: User | None = None,
    name: str | None = None,
    dataset: Dataset | None = None,
    **overrides,
) -> EvaluationConfig:
    """Create a test evaluation config."""
    n = _next_id()
    if organization is None:
        organization = await create_organization(db)
    if user is None:
        user = await create_user(db, organization=organization)

    config = EvaluationConfig(
        name=name or f"Test Config {n}",
        organization_id=organization.id,
        created_by_id=user.id,
        dataset_id=dataset.id if dataset else None,
        model_config_data={"provider": "openai", "model": "gpt-4"},
        metrics_config=[{"metric_type": "accuracy", "weight": 1.0}],
        parameters={"batch_size": 10},
        **overrides,
    )
    db.add(config)
    await db.flush()
    return config


async def create_evaluation_run(
    db,
    *,
    config: EvaluationConfig | None = None,
    organization: Organization | None = None,
    user: User | None = None,
    status: RunStatus = RunStatus.PENDING,
    **overrides,
) -> EvaluationRun:
    """Create a test evaluation run."""
    if organization is None:
        organization = await create_organization(db)
    if user is None:
        user = await create_user(db, organization=organization)
    if config is None:
        config = await create_evaluation_config(
            db, organization=organization, user=user
        )

    run = EvaluationRun(
        config_id=config.id,
        organization_id=organization.id,
        triggered_by_id=user.id,
        status=status,
        total_samples=100,
        run_metadata={},
        **overrides,
    )
    db.add(run)
    await db.flush()
    return run


async def create_metric(
    db,
    *,
    organization: Organization | None = None,
    name: str | None = None,
    is_builtin: bool = False,
    **overrides,
) -> Metric:
    """Create a test metric."""
    n = _next_id()
    org_id = None
    if not is_builtin:
        if organization is None:
            organization = await create_organization(db)
        org_id = organization.id

    metric = Metric(
        name=name or f"test_metric_{n}",
        display_name=f"Test Metric {n}",
        description="A test metric",
        organization_id=org_id,
        metric_type=MetricType.CUSTOM,
        computation_config={},
        higher_is_better=True,
        min_value=0.0,
        max_value=1.0,
        is_builtin=is_builtin,
        **overrides,
    )
    db.add(metric)
    await db.flush()
    return metric


async def create_api_key(
    db,
    *,
    user: User | None = None,
    organization: Organization | None = None,
    name: str = "Test API Key",
    **overrides,
) -> tuple[ApiKey, str]:
    """Create a test API key. Returns (api_key, raw_key)."""
    from src.security import generate_api_key

    if organization is None:
        organization = await create_organization(db)
    if user is None:
        user = await create_user(db, organization=organization)

    raw_key, key_hash, key_prefix = generate_api_key()

    api_key = ApiKey(
        name=name,
        key_hash=key_hash,
        key_prefix=key_prefix,
        user_id=user.id,
        organization_id=organization.id,
        scopes=["evaluations:read", "evaluations:write"],
        **overrides,
    )
    db.add(api_key)
    await db.flush()
    return api_key, raw_key


async def create_submission(
    db,
    *,
    organization: Organization | None = None,
    user: User | None = None,
    startup_name: str | None = None,
    status: str = "draft",
    **overrides,
) -> Submission:
    """Create a test submission."""
    from src.models.submission import Submission, SubmissionStatus

    n = _next_id()
    if organization is None:
        organization = await create_organization(db)
    if user is None:
        user = await create_user(db, organization=organization)

    submission = Submission(
        organization_id=organization.id,
        submitted_by_id=user.id,
        startup_name=startup_name or f"Test Startup {n}",
        status=SubmissionStatus(status),
        description=f"Description for Test Startup {n}",
        website_url=f"https://startup{n}.test",
        metadata_={},
        **overrides,
    )
    db.add(submission)
    await db.flush()
    return submission
