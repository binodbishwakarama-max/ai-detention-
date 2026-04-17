"""Unit tests for metric service."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.error_handler import ConflictError, NotFoundError
from src.models.metric import MetricType
from src.services.metric_service import (
    create_custom_metric,
    get_metric,
    list_metrics,
    seed_builtin_metrics,
)
from tests.factories import create_metric, create_organization, create_user


@pytest.mark.asyncio
class TestMetricService:
    async def test_seed_builtin_metrics_is_idempotent(
        self, db_session: AsyncSession
    ):
        # Seed once
        count1 = await seed_builtin_metrics(db_session)
        assert count1 > 0

        # Seed again - should create 0
        count2 = await seed_builtin_metrics(db_session)
        assert count2 == 0

    async def test_create_custom_metric(self, db_session: AsyncSession):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)

        metric = await create_custom_metric(
            db_session,
            org_id=org.id,
            user_id=user.id,
            name="custom_score",
            display_name="Custom Score",
            metric_type=MetricType.CUSTOM,
            higher_is_better=True,
            min_value=0.0,
            max_value=100.0,
        )

        assert metric.name == "custom_score"
        assert metric.organization_id == org.id
        assert metric.is_builtin is False
        assert metric.higher_is_better is True

    async def test_duplicate_custom_metric_name_raises(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)

        await create_custom_metric(
            db_session,
            org_id=org.id,
            user_id=user.id,
            name="dupe_score",
            display_name="Dupe",
        )

        with pytest.raises(ConflictError, match="already exists"):
            await create_custom_metric(
                db_session,
                org_id=org.id,
                user_id=user.id,
                name="dupe_score",
                display_name="Dupe 2",
            )

    async def test_list_metrics_returns_builtin_and_custom(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)

        await seed_builtin_metrics(db_session)
        builtin_count = (await list_metrics(db_session, org_id=org.id, page=1, page_size=100))[1]

        await create_custom_metric(
            db_session,
            org_id=org.id,
            user_id=user.id,
            name="org_metric_1",
            display_name="Metric 1",
        )
        await create_custom_metric(
            db_session,
            org_id=org.id,
            user_id=user.id,
            name="org_metric_2",
            display_name="Metric 2",
        )

        metrics, total = await list_metrics(
            db_session, org_id=org.id, page=1, page_size=100
        )
        assert total == builtin_count + 2

        # Verify cross-org isolation
        org2 = await create_organization(db_session)
        metrics2, total2 = await list_metrics(
            db_session, org_id=org2.id, page=1, page_size=100
        )
        assert total2 == builtin_count

    async def test_get_metric_success(self, db_session: AsyncSession):
        org = await create_organization(db_session)
        custom = await create_metric(db_session, organization=org)
        builtin = await create_metric(db_session, is_builtin=True)

        # Can get own custom metric
        fetched1 = await get_metric(
            db_session, metric_id=custom.id, org_id=org.id
        )
        assert fetched1.id == custom.id

        # Can get global built-in metric
        fetched2 = await get_metric(
            db_session, metric_id=builtin.id, org_id=org.id
        )
        assert fetched2.id == builtin.id

    async def test_get_metric_by_id(self, db_session: AsyncSession):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        metric = await create_metric(db_session, organization=org, user=user)

        fetched_metric = await get_metric(
            db_session, metric_id=metric.id, org_id=org.id
        )
        assert fetched_metric.id == metric.id
        assert fetched_metric.name == metric.name

    async def test_get_metric_not_found_raises(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        import uuid

        with pytest.raises(NotFoundError):
            await get_metric(
                db_session, metric_id=uuid.uuid4(), org_id=org.id
            )
