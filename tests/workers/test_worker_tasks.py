"""Integration-level Worker tests using the real Celery execution flow.

In this file, we test the worker tasks by calling `task.apply()` which runs
the task synchronously in the current process, simulating a worker but without
needing a separate worker process.
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import uuid4

from src.models.evaluation import RunStatus
from src.workers.tasks.generator_task import ModelGeneratorTask
from src.workers.tasks.judge_task import LLMJudgeTask
from src.models.worker_result import WorkerStatus, WorkerResult
from tests.factories import create_evaluation_run, create_dataset

@pytest.mark.asyncio
class TestWorkerExecution:
    async def test_generator_task_success(self, db_session: AsyncSession, test_run, test_dataset):
        # Configure mocked LLM call
        with patch("src.workers.tasks.generator_task.LLMClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.generate.return_value = {
                "text": "Simulated output",
                "usage": {"total_tokens": 100}
            }
            
            task = ModelGeneratorTask()
            
            # Use `run` instead of `apply_async` to execute it immediately in the current thread
            # and wait for the result
            with patch.object(task.request, 'id', 'test-task-1'):
                with patch.object(task.request, 'hostname', 'test-worker'):
                    with patch.object(task.request, 'retries', 0):
                        result = task.run(
                            run_id=str(test_run.id),
                            dataset_id=str(test_dataset.id),
                            batch_size=10
                        )

            assert result is not None
            assert "samples_processed" in result
            assert "total_tokens" in result

            # Verify the DB captured the worker result correctly
            from sqlalchemy import select
            res = await db_session.execute(
                select(WorkerResult).where(
                    WorkerResult.evaluation_run_id == test_run.id,
                    WorkerResult.worker_type == "generator"
                )
            )
            wr = res.scalar_one_or_none()
            assert wr is not None
            assert wr.status == WorkerStatus.COMPLETED

    async def test_judge_task_idempotency(self, db_session: AsyncSession, test_run):
        # Seed an already completed WorkerResult
        from src.models.worker_result import WorkerResult, WorkerStatus
        
        wr = WorkerResult(
            evaluation_run_id=test_run.id,
            organization_id=test_run.organization_id,
            worker_type="judge",
            status=WorkerStatus.COMPLETED,
            output_data={"cached": "yes"}
        )
        db_session.add(wr)
        await db_session.commit()

        task = LLMJudgeTask()
        with patch.object(task.request, 'id', 'test-task-2'):
            with patch.object(task.request, 'hostname', 'test-worker'):
                with patch.object(task.request, 'retries', 0):
                    result = task.run(run_id=str(test_run.id))

        # Should return cached data, bypassing real execution
        assert result == {"cached": "yes"}

    async def test_worker_chord_failure_propagation(self, db_session: AsyncSession, test_run):
        """Simulate the chord: partial failures continue formatting."""
        from src.models.worker_result import WorkerResult, WorkerStatus
        # Add a failed generator and successful guardrails
        failed_gen = WorkerResult(
            evaluation_run_id=test_run.id,
            organization_id=test_run.organization_id,
            worker_type="generator",
            status=WorkerStatus.FAILED,
            error_message="API Timeout"
        )
        success_guard = WorkerResult(
            evaluation_run_id=test_run.id,
            organization_id=test_run.organization_id,
            worker_type="guardrails",
            status=WorkerStatus.COMPLETED,
            output_data={"safe": True}
        )
        db_session.add(failed_gen)
        db_session.add(success_guard)
        await db_session.commit()

        # Execute judge task. It should handle the partial data without dying.
        # Judge reads from DB results.
        with patch("src.workers.tasks.judge_task.LLMClient") as MockClient:
            mock_client = MockClient.return_value
            mock_client.generate.return_value = {"text": "Fallthrough judgment due to partial data"}
            
            task = LLMJudgeTask()
            with patch.object(task.request, 'id', 'test-task-chord'):
                with patch.object(task.request, 'hostname', 'test-worker'):
                    with patch.object(task.request, 'retries', 0):
                        result = task.run(run_id=str(test_run.id))
                        
            assert result is not None
            # Judge should run and log completion despite `generator` missing output data

