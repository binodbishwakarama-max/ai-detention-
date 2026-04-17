"""
Pytest fixtures and configuration for the test suite.

Architecture:
- SQLite in-memory for fast, isolated unit tests
- Shared session scoped per-test for automatic cleanup
- TestClient with dependency overrides for integration tests
- Mock S3 via moto for storage tests
- Auth helpers for authenticated requests

Targets:
- pytest-xdist compatible (no shared state between workers)
- < 3 minute total runtime
- 95%+ coverage
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from typing import Generator
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from src.config import Settings, get_settings
from src.database import get_db_session
from src.models.base import Base
from src.security import Role, hash_password


# ── Settings Override ────────────────────────────────────────

def get_test_settings(pg_url: str, redis_url: str, redis_broker: str) -> Settings:
    """Return settings configured for testing."""
    return Settings(
        app_env="testing",
        secret_key="test-secret-key-not-for-production-1234567890",
        database_url=pg_url,
        redis_url=redis_url,
        celery_broker_url=redis_broker,
        celery_result_backend=redis_broker,
        s3_endpoint_url="https://s3.amazonaws.com", # Mocked by moto
        s3_access_key_id="test",
        s3_secret_access_key="test",
        s3_bucket_name="test-bucket",
        cors_origins=["*"],
        jwt_access_token_expire_minutes=30,
        otel_enabled=False,  # Disable tracing in tests
    )


# ── Infrastructure Fixtures ─────────────────────────────────

@pytest.fixture(scope="session")
def postgres_container():
    """Start Postgres in testcontainers for the session."""
    import warnings
    # Ignore resource warnings from testcontainers background threads
    warnings.filterwarnings("ignore", category=ResourceWarning)
    
    from testcontainers.postgres import PostgresContainer
    with PostgresContainer("postgres:16-alpine") as postgres:
        # Get asyncpg URL
        url = postgres.get_connection_url().replace("postgresql+psycopg2", "postgresql+asyncpg")
        yield url

@pytest_asyncio.fixture(scope="session")
async def pg_engine(postgres_container):
    """Provide a SQLAlchemy async engine for the entire test session."""
    engine = create_async_engine(postgres_container, echo=False)
    # Create tables once per session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    # Drop not strictly active because container dies, but clean
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest.fixture
def redis_container():
    """Start Redis testcontainer per test for strict isolation."""
    from testcontainers.redis import RedisContainer
    with RedisContainer("redis:7-alpine") as redis:
        yield f"redis://{redis.get_container_host_ip()}:{redis.get_exposed_port(6379)}/0"

@pytest.fixture
def mock_s3_moto():
    """Mock AWS S3 using moto."""
    import os
    from moto import mock_aws
    import boto3

    # Ensure no accidental real AWS calls
    os.environ["AWS_ACCESS_KEY_ID"] = "test"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
    os.environ["AWS_SECURITY_TOKEN"] = "test"
    os.environ["AWS_SESSION_TOKEN"] = "test"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"

    with mock_aws():
        # Create the bucket
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        yield s3


# ── Database Session ────────────────────────────────────────

@pytest_asyncio.fixture
async def db_session(pg_engine) -> AsyncGenerator[AsyncSession, None]:
    """
    Provide an isolated database session per test.
    Instead of recreating tables, we use nested transactions (savepoints)
    and rollback at the end of the test.
    """
    async with pg_engine.connect() as conn:
        await conn.begin() # Start transaction
        async with AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint"
        ) as session:
            yield session
        await conn.rollback() # Rollback at the end to keep DB pristine for next test


# ── HTTP Client Fixture ─────────────────────────────────────

@pytest_asyncio.fixture
async def client(
    db_session: AsyncSession,
    postgres_container: str,
    redis_container: str,
    mock_s3_moto
) -> AsyncGenerator[AsyncClient, None]:
    """
    Provide an async HTTP test client with dependency overrides.
    """
    from src.main import app

    # Override dependencies
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def override_get_settings():
        return get_test_settings(postgres_container, redis_container, redis_container)

    app.dependency_overrides[get_db_session] = override_get_db
    app.dependency_overrides[get_settings] = override_get_settings

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport, base_url="http://test"
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Data Factory Fixtures ──────────────────────────────────────


@pytest_asyncio.fixture
async def test_org(db_session: AsyncSession):
    """Create a test organization."""
    from tests.factories import create_organization

    return await create_organization(db_session)


@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession, test_org):
    """Create a test user."""
    from tests.factories import create_user

    return await create_user(
        db_session,
        organization=test_org,
        email="test@example.com",
        role=Role.ADMIN,
    )


@pytest_asyncio.fixture
async def test_viewer(db_session: AsyncSession, test_org):
    """Create a test user with VIEWER role."""
    from tests.factories import create_user

    return await create_user(
        db_session,
        organization=test_org,
        email="viewer@example.com",
        role=Role.VIEWER,
    )


@pytest_asyncio.fixture
async def test_member(db_session: AsyncSession, test_org):
    """Create a test user with MEMBER role."""
    from tests.factories import create_user

    return await create_user(
        db_session,
        organization=test_org,
        email="member@example.com",
        role=Role.MEMBER,
    )


@pytest_asyncio.fixture
async def test_dataset(db_session: AsyncSession, test_org, test_user):
    """Create a test dataset."""
    from tests.factories import create_dataset

    return await create_dataset(
        db_session,
        organization=test_org,
        user=test_user,
    )


@pytest_asyncio.fixture
async def test_config(db_session: AsyncSession, test_org, test_user):
    """Create a test evaluation config."""
    from tests.factories import create_evaluation_config

    return await create_evaluation_config(
        db_session,
        organization=test_org,
        user=test_user,
    )


@pytest_asyncio.fixture
async def test_run(db_session: AsyncSession, test_config, test_org, test_user):
    """Create a test evaluation run."""
    from tests.factories import create_evaluation_run

    return await create_evaluation_run(
        db_session,
        config=test_config,
        organization=test_org,
        user=test_user,
    )


# ── Auth Fixtures ────────────────────────────────────────────


@pytest_asyncio.fixture
async def auth_headers(test_user) -> dict[str, str]:
    """Generate authentication headers for a test user."""
    from src.security import create_access_token

    token = create_access_token(
        test_user.id,
        test_user.organization_id,
        test_user.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def viewer_headers(test_viewer) -> dict[str, str]:
    """Generate authentication headers for a viewer user."""
    from src.security import create_access_token

    token = create_access_token(
        test_viewer.id,
        test_viewer.organization_id,
        test_viewer.role,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def member_headers(test_member) -> dict[str, str]:
    """Generate authentication headers for a member user."""
    from src.security import create_access_token

    token = create_access_token(
        test_member.id,
        test_member.organization_id,
        test_member.role,
    )
    return {"Authorization": f"Bearer {token}"}


# ── Mock Fixtures ────────────────────────────────────────────


@pytest.fixture
def mock_celery():
    """Mock Celery task dispatch to prevent actual worker execution."""
    with patch(
        "src.workers.evaluation_worker.execute_evaluation_run.delay"
    ) as mock:
        mock.return_value = AsyncMock(id="test-celery-task-id")
        yield mock


@pytest.fixture
def mock_s3():
    """Mock S3 operations for storage tests."""
    with patch("src.s3_client.get_s3_client") as mock:
        mock_client = AsyncMock()
        mock.return_value = mock_client
        yield mock_client


@pytest.fixture
def mock_redis():
    """Mock Redis for cache tests."""
    with patch("src.redis_client.get_redis") as mock:
        mock_redis = AsyncMock()
        mock_redis.ping.return_value = True
        mock_redis.get.return_value = None
        mock.return_value = mock_redis
        yield mock_redis
