"""Unit tests for evaluation service."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.error_handler import ConflictError, NotFoundError
from src.models.evaluation import RunStatus
from src.services.evaluation_service import (
    cancel_evaluation_run,
    create_evaluation_config,
    create_evaluation_run,
    delete_evaluation_config,
    get_evaluation_config,
    list_evaluation_configs,
    update_evaluation_config,
)
from tests.factories import (
    create_dataset,
    create_evaluation_config as factory_config,
    create_evaluation_run as factory_run,
    create_organization,
    create_user,
)


@pytest.mark.asyncio
class TestEvaluationConfigCRUD:
    async def test_create_config(self, db_session: AsyncSession):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)

        config = await create_evaluation_config(
            db_session,
            org_id=org.id,
            user_id=user.id,
            name="My Config",
            model_config={"provider": "openai"},
        )
        assert config.name == "My Config"
        assert config.version == 1
        assert config.organization_id == org.id

    async def test_create_config_with_invalid_dataset_raises(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        import uuid

        with pytest.raises(NotFoundError):
            await create_evaluation_config(
                db_session,
                org_id=org.id,
                user_id=user.id,
                name="Bad DS",
                dataset_id=uuid.uuid4(),
            )

    async def test_get_config_not_found_raises(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        import uuid

        with pytest.raises(NotFoundError):
            await get_evaluation_config(
                db_session, config_id=uuid.uuid4(), org_id=org.id
            )

    async def test_list_configs_pagination(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)

        for i in range(5):
            await factory_config(
                db_session,
                organization=org,
                user=user,
                name=f"Config {i}",
            )

        configs, total = await list_evaluation_configs(
            db_session, org_id=org.id, page=1, page_size=3
        )
        assert total == 5
        assert len(configs) == 3

        configs2, _ = await list_evaluation_configs(
            db_session, org_id=org.id, page=2, page_size=3
        )
        assert len(configs2) == 2

    async def test_update_config_increments_version(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        config = await factory_config(
            db_session, organization=org, user=user
        )
        assert config.version == 1

        updated = await update_evaluation_config(
            db_session,
            config_id=config.id,
            org_id=org.id,
            user_id=user.id,
            updates={"name": "Updated"},
        )
        assert updated.version == 2
        assert updated.name == "Updated"

    async def test_delete_config_soft_deletes(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        config = await factory_config(
            db_session, organization=org, user=user
        )
        await delete_evaluation_config(
            db_session,
            config_id=config.id,
            org_id=org.id,
            user_id=user.id,
        )
        with pytest.raises(NotFoundError):
            await get_evaluation_config(
                db_session, config_id=config.id, org_id=org.id
            )


@pytest.mark.asyncio
class TestEvaluationRunLifecycle:
    async def test_create_run(self, db_session: AsyncSession):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        config = await factory_config(db_session, organization=org, user=user)

        run = await create_evaluation_run(
            db_session,
            config=config,
            user_id=user.id,
            org_id=org.id,
        )
        assert run.config_id == config.id
        assert run.status == RunStatus.PENDING
        assert run.organization_id == org.id

    async def test_cancel_run(self, db_session: AsyncSession):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        config = await factory_config(db_session, organization=org, user=user)
        run = await factory_run(
            db_session,
            organization=org,
            user=user,
            config=config,
            status=RunStatus.RUNNING,
        )

        cancelled_run = await cancel_evaluation_run(
            db_session,
            run_id=run.id,
            org_id=org.id,
            user_id=user.id,
        )
        assert cancelled_run.status == RunStatus.CANCELED

    async def test_cancel_completed_run_raises_conflict(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        config = await factory_config(db_session, organization=org, user=user)
        run = await factory_run(
            db_session,
            organization=org,
            user=user,
            config=config,
            status=RunStatus.COMPLETED,
        )

        with pytest.raises(ConflictError, match="terminal state"):
            await cancel_evaluation_run(
                db_session,
                run_id=run.id,
                org_id=org.id,
                user_id=user.id,
            )

    async def test_create_run_dispatches_celery(
        self, db_session: AsyncSession
    ):
        """Creating a run should dispatch to Celery."""
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        config = await factory_config(
            db_session, organization=org, user=user
        )

        with patch(
            "src.services.evaluation_service.execute_evaluation_run"
        ) as mock_worker:
            mock_task = AsyncMock()
            mock_task.id = "celery-123"
            mock_worker.delay.return_value = mock_task

            run = await create_evaluation_run(
                db_session,
                config_id=config.id,
                org_id=org.id,
                user_id=user.id,
            )
            assert run.status == RunStatus.PENDING
            assert run.celery_task_id == "celery-123"
            mock_worker.delay.assert_called_once()

    async def test_cancel_terminal_run_raises_conflict(
        self, db_session: AsyncSession
    ):
        """Cannot cancel a run that is already completed."""
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        run = await factory_run(
            db_session,
            organization=org,
            user=user,
            status=RunStatus.COMPLETED,
        )
        with pytest.raises(ConflictError, match="Cannot cancel"):
            await cancel_evaluation_run(
                db_session,
                run_id=run.id,
                org_id=org.id,
                user_id=user.id,
            )

    async def test_concurrent_eval_limit_enforced(
        self, db_session: AsyncSession
    ):
        """Cannot exceed max concurrent evaluations."""
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        config = await factory_config(
            db_session, organization=org, user=user
        )

        # Create runs up to the limit
        for _ in range(org.max_concurrent_evaluations):
            await factory_run(
                db_session,
                config=config,
                organization=org,
                user=user,
                status=RunStatus.RUNNING,
            )

        with patch(
            "src.services.evaluation_service.execute_evaluation_run"
        ):
            with pytest.raises(ConflictError, match="Maximum concurrent"):
                await create_evaluation_run(
                    db_session,
                    config_id=config.id,
                    org_id=org.id,
                    user_id=user.id,
                )
