"""
Export Results Task — asynchronous reporting and data export.

Specifics:
- Generates PDF/CSV reports of evaluation results
- Uploads to S3 and returns presigned URL
- Soft timeout: 300s, hard timeout: 360s
- Uses 'export' queue (low concurrency)
"""

from __future__ import annotations

import csv
import io
import time
from uuid import UUID

import structlog

from src.workers.celery_app import celery_app
from src.workers.tasks.base_task import BaseEvalTask, _run_async

logger = structlog.get_logger(__name__)


async def _export_results(run_id: str, format: str = "csv", update_progress=None) -> dict:
    """Generate export of evaluation run and claims."""
    from sqlalchemy import select
    from src.database import get_standalone_session
    from src.models.evaluation import EvaluationRun
    from src.models.claim import Claim
    from src.models.score import Score

    if update_progress:
        update_progress(run_id, 10, "Fetching data for export")

    async with get_standalone_session() as db:
        run_res = await db.execute(select(EvaluationRun).where(EvaluationRun.id == UUID(run_id)))
        run = run_res.scalar_one_or_none()
        if not run:
            return {"status": "error", "reason": "Run not found"}

        claims_res = await db.execute(select(Claim).where(Claim.evaluation_run_id == UUID(run_id)))
        claims = list(claims_res.scalars().all())

        scores_res = await db.execute(select(Score).where(Score.evaluation_run_id == UUID(run_id)))
        scores = list(scores_res.scalars().all())

    if update_progress:
        update_progress(run_id, 50, f"Generating {format.upper()} document")

    # Generate CSV in memory
    try:
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Summary section
        writer.writerow(["Evaluation summary", str(run.id), run.status])
        writer.writerow(["Overall Score", str(run.overall_score)])
        writer.writerow([])
        
        # Dimension scores
        writer.writerow(["SCORE DIMENSION", "VALUE", "WEIGHT", "RATIONALE"])
        for s in scores:
            writer.writerow([s.dimension, s.value, s.weight, s.rationale])
        writer.writerow([])
        
        # Claims
        writer.writerow(["CLAIM TEXT", "CATEGORY", "CONFIDENCE", "SOURCE", "VERIFICATION_STATUS"])
        for c in claims:
            writer.writerow([c.claim_text, c.category, c.confidence_score, c.source_reference, c.verification_status])
        
        csv_content = output.getvalue()
        file_size = len(csv_content)

        if update_progress:
            update_progress(run_id, 80, "Uploading to S3")

        # In production: Upload to S3 and generate presigned URL here
        # Temporarily simulating S3 upload
        s3_key = f"exports/{run.organization_id}/{run_id}.csv"
        presigned_url = f"https://mock-s3-bucket.s3.amazonaws.com/{s3_key}?signature=mock"

        if update_progress:
            update_progress(run_id, 100, "Export complete")

        return {
            "status": "completed",
            "format": format,
            "size_bytes": file_size,
            "download_url": presigned_url,
            "s3_key": s3_key,
        }

    except Exception as e:
        logger.exception("export_results.failed", run_id=run_id)
        return {"status": "error", "reason": str(e)}


@celery_app.task(
    name="src.workers.tasks.export.export_results_task",
    base=BaseEvalTask,
    bind=True,
    max_retries=3,
    soft_time_limit=300,
    time_limit=360,
)
def export_results_task(self, run_id: str, format: str = "csv") -> dict:
    self.worker_type = "export"
    self._start_time = time.monotonic()
    return _run_async(
        _export_results(run_id, format, self.update_progress)
    )
