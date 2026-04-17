"""Integration tests for dataset endpoints."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from src.models.dataset import DatasetStatus


@pytest.mark.asyncio
class TestDatasetEndpoints:
    async def test_dataset_upload_lifecycle(
        self, client: AsyncClient, auth_headers, mock_s3
    ):
        """Test the full presigned URL upload flow."""
        # 1. Initiate upload
        init_response = await client.post(
            "/api/v1/datasets",
            headers=auth_headers,
            json={
                "name": "Integration Test Dataset",
                "size_bytes": 1048576,  # 1MB
            },
        )
        assert init_response.status_code == 201
        data = init_response.json()
        assert data["upload_url"] is not None
        assert data["dataset"]["status"] == DatasetStatus.UPLOADING.value
        dataset_id = data["dataset"]["id"]

        # 2. In a real scenario, the client uploads to S3 here.
        # We simulate this and then confirm the upload.
        
        # 3. Confirm upload
        with pytest.patch(
            "src.services.dataset_service.verify_dataset_integrity",
            return_value=True,
        ):
            confirm_response = await client.post(
                f"/api/v1/datasets/{dataset_id}/confirm",
                headers=auth_headers,
                json={
                    "checksum": "sha256-dummy",
                    "sample_count": 100,
                },
            )
        
        assert confirm_response.status_code == 200
        confirm_data = confirm_response.json()
        assert confirm_data["status"] == DatasetStatus.READY.value
        assert confirm_data["sample_count"] == 100

        # 4. List datasets to ensure it shows up
        list_response = await client.get(
            "/api/v1/datasets",
            headers=auth_headers,
        )
        assert list_response.status_code == 200
        datasets = list_response.json()["data"]
        assert len(datasets) > 0
        assert any(d["id"] == dataset_id for d in datasets)

    async def test_dataset_deletion(
        self, client: AsyncClient, auth_headers, test_dataset
    ):
        """Test deleting a dataset via the API."""
        # 1. Ensure the dataset exists
        get_response = await client.get(
            f"/api/v1/datasets/{test_dataset.id}",
            headers=auth_headers,
        )
        assert get_response.status_code == 200

        # 2. Delete it
        delete_response = await client.delete(
            f"/api/v1/datasets/{test_dataset.id}",
            headers=auth_headers,
        )
        assert delete_response.status_code == 204

        # 3. Ensure it is gone
        get_response_after = await client.get(
            f"/api/v1/datasets/{test_dataset.id}",
            headers=auth_headers,
        )
        assert get_response_after.status_code == 404

    async def test_viewer_cannot_create_dataset(
        self, client: AsyncClient, viewer_headers
    ):
        """RBAC test: viewers cannot write datasets."""
        response = await client.post(
            "/api/v1/datasets",
            headers=viewer_headers,
            json={
                "name": "Hacker Dataset",
                "size_bytes": 1024,
            },
        )
        assert response.status_code == 403
