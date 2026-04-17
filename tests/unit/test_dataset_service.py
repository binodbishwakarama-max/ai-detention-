"""Unit tests for dataset service."""

from __future__ import annotations

from unittest.mock import patch
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.middleware.error_handler import ConflictError, NotFoundError
from src.models.dataset import DatasetStatus
from src.services.dataset_service import (
    confirm_dataset_upload,
    delete_dataset,
    get_dataset,
    initiate_dataset_upload,
    list_datasets,
)
from tests.factories import create_dataset, create_organization, create_user


@pytest.mark.asyncio
class TestDatasetLifecycle:
    async def test_initiate_upload_returns_presigned_url(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)

        with patch("src.s3_client.generate_presigned_url") as mock_url:
            mock_url.return_value = "https://s3.example.com/upload"

            dataset, upload_url = await initiate_dataset_upload(
                db_session,
                org_id=org.id,
                user_id=user.id,
                name="My Dataset",
                size_bytes=1024,
            )

            assert dataset.name == "My Dataset"
            assert dataset.status == DatasetStatus.UPLOADING
            assert upload_url == "https://s3.example.com/upload"
            assert dataset.organization_id == org.id

    async def test_confirm_upload_transitions_to_ready(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        dataset = await create_dataset(
            db_session,
            organization=org,
            user=user,
            status=DatasetStatus.UPLOADING,
        )

        with patch(
            "src.services.dataset_service.verify_dataset_integrity"
        ) as mock_verify:
            mock_verify.return_value = True

            ready_dataset = await confirm_dataset_upload(
                db_session,
                dataset_id=dataset.id,
                org_id=org.id,
                checksum="sha256-12345",
                sample_count=50,
            )

            assert ready_dataset.status == DatasetStatus.READY
            assert ready_dataset.sample_count == 50
            assert ready_dataset.checksum == "sha256-12345"

    async def test_confirm_upload_fails_on_bad_checksum(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        dataset = await create_dataset(
            db_session,
            organization=org,
            user=user,
            status=DatasetStatus.UPLOADING,
        )

        with patch(
            "src.services.dataset_service.verify_dataset_integrity"
        ) as mock_verify:
            mock_verify.return_value = False

            with pytest.raises(ConflictError, match="Checksum"):
                await confirm_dataset_upload(
                    db_session,
                    dataset_id=dataset.id,
                    org_id=org.id,
                    checksum="sha256-bad",
                    sample_count=50,
                )

            # verify it was put into FAILED state
            await db_session.refresh(dataset)
            assert dataset.status == DatasetStatus.FAILED

    async def test_confirm_upload_wrong_state_raises(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        dataset = await create_dataset(
            db_session,
            organization=org,
            user=user,
            status=DatasetStatus.READY,  # already ready
        )

        with pytest.raises(ConflictError, match="uploading"):
            await confirm_dataset_upload(
                db_session,
                dataset_id=dataset.id,
                org_id=org.id,
                checksum="sha256-123",
                sample_count=10,
            )


@pytest.mark.asyncio
class TestDatasetCRUD:
    async def test_get_dataset_success(self, db_session: AsyncSession):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        dataset = await create_dataset(
            db_session, organization=org, user=user
        )

        fetched = await get_dataset(
            db_session, dataset_id=dataset.id, org_id=org.id
        )
        assert fetched.id == dataset.id

    async def test_get_dataset_wrong_org_raises(
        self, db_session: AsyncSession
    ):
        org1 = await create_organization(db_session)
        org2 = await create_organization(db_session)
        user = await create_user(db_session, organization=org1)
        dataset = await create_dataset(
            db_session, organization=org1, user=user
        )

        with pytest.raises(NotFoundError):
            await get_dataset(
                db_session, dataset_id=dataset.id, org_id=org2.id
            )

    async def test_list_datasets_pagination(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)

        for _ in range(5):
            await create_dataset(
                db_session, organization=org, user=user
            )

        datasets, total = await list_datasets(
            db_session, org_id=org.id, page=1, page_size=3
        )
        assert total == 5
        assert len(datasets) == 3

    async def test_delete_dataset_is_soft_delete(
        self, db_session: AsyncSession
    ):
        org = await create_organization(db_session)
        user = await create_user(db_session, organization=org)
        dataset = await create_dataset(
            db_session, organization=org, user=user
        )

        await delete_dataset(
            db_session,
            dataset_id=dataset.id,
            org_id=org.id,
            user_id=user.id,
        )

        with pytest.raises(NotFoundError):
            await get_dataset(
                db_session, dataset_id=dataset.id, org_id=org.id
            )
