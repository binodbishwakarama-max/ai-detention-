"""
Cross-Check Task — detects contradictions between claims from different sources.

Receives aggregated results from all 4 analysis workers.
Compares claims across sources to detect inconsistencies.
"""

from __future__ import annotations

import time
from uuid import UUID

import structlog

from src.workers.celery_app import celery_app
from src.workers.tasks.base_task import BaseEvalTask, _run_async

logger = structlog.get_logger(__name__)


async def _cross_check(
    run_id: str,
    parallel_results: list[dict],
    update_progress,
) -> dict:
    """
    Cross-check claims from all parallel analysis tasks.

    Compares claims pairwise to detect contradictions:
    e.g., GitHub says "2 contributors" but pitch deck says "team of 20"
    """
    from src.database import get_standalone_session
    from src.models.claim import Claim
    from src.models.contradiction import Contradiction
    from src.models.evaluation import EvaluationRun
    from sqlalchemy import select

    update_progress(run_id, 10, "Collecting claims from all sources")

    # ── Step 1: Aggregate all claims from parallel results ─
    all_claims = []
    for task_result in parallel_results:
        if isinstance(task_result, dict):
            claims = task_result.get("claims", [])
            source = task_result.get("status", "unknown")
            for claim in claims:
                claim["source_task"] = source
                all_claims.append(claim)

    if len(all_claims) < 2:
        return {
            "status": "completed",
            "contradictions_found": 0,
            "claims_analyzed": len(all_claims),
        }

    update_progress(run_id, 30, f"Analyzing {len(all_claims)} claims for contradictions")

    # ── Step 2: Store claims in database ─────────────────
    async with get_standalone_session() as db:
        run_result = await db.execute(
            select(EvaluationRun).where(EvaluationRun.id == UUID(run_id))
        )
        run = run_result.scalar_one()

        stored_claims = []
        for claim_data in all_claims:
            claim = Claim(
                evaluation_run_id=run.id,
                submission_id=run.submission_id,
                organization_id=run.organization_id,
                claim_text=claim_data.get("text", ""),
                category=claim_data.get("category", "general"),
                confidence_score=claim_data.get("confidence", 0.5),
                source_reference=claim_data.get("source_reference", ""),
                evidence={"source_task": claim_data.get("source_task", "")},
            )
            db.add(claim)
            stored_claims.append(claim)

        await db.flush()

        update_progress(run_id, 50, "Detecting contradictions")

        # ── Step 3: Pairwise contradiction detection ─────
        contradictions = []
        for i in range(len(stored_claims)):
            for j in range(i + 1, len(stored_claims)):
                claim_a = stored_claims[i]
                claim_b = stored_claims[j]

                # Skip same-category comparisons that are likely consistent
                if claim_a.category != claim_b.category:
                    continue

                # Detect numerical contradictions
                contradiction = _detect_contradiction(
                    claim_a.claim_text, claim_b.claim_text
                )

                if contradiction:
                    c = Contradiction(
                        evaluation_run_id=run.id,
                        organization_id=run.organization_id,
                        claim_a_id=claim_a.id,
                        claim_b_id=claim_b.id,
                        contradiction_type=contradiction["type"],
                        severity=contradiction["severity"],
                        explanation=contradiction["explanation"],
                    )
                    db.add(c)
                    contradictions.append({
                        "claim_a": claim_a.claim_text,
                        "claim_b": claim_b.claim_text,
                        "type": contradiction["type"],
                        "severity": contradiction["severity"],
                    })

            # Progress update per claim
            progress = 50 + int((i / len(stored_claims)) * 40)
            update_progress(run_id, min(90, progress), "Comparing claims")

        await db.flush()

    return {
        "status": "completed",
        "claims_stored": len(stored_claims),
        "contradictions_found": len(contradictions),
        "contradictions": contradictions[:20],  # top 20 for size limit
    }


def _detect_contradiction(text_a: str, text_b: str) -> dict | None:
    """
    Simple contradiction detection between two claim texts.

    In production: use an LLM for semantic contradiction detection.
    """
    import re

    # Extract numbers from both claims
    nums_a = re.findall(r"\d+(?:\.\d+)?", text_a)
    nums_b = re.findall(r"\d+(?:\.\d+)?", text_b)

    if nums_a and nums_b:
        # Check if numbers differ significantly
        for na in nums_a:
            for nb in nums_b:
                va, vb = float(na), float(nb)
                if va > 0 and vb > 0:
                    ratio = max(va, vb) / min(va, vb)
                    if ratio > 3:  # 3x difference = contradiction
                        severity = min(1.0, ratio / 10)
                        return {
                            "type": "numerical",
                            "severity": round(severity, 2),
                            "explanation": (
                                f"Numerical inconsistency: "
                                f"'{text_a}' vs '{text_b}' "
                                f"(ratio: {ratio:.1f}x)"
                            ),
                        }
    return None


@celery_app.task(
    name="src.workers.tasks.cross_check.cross_check_task",
    base=BaseEvalTask,
    bind=True,
    max_retries=3,
    soft_time_limit=120,
    time_limit=150,
)
def cross_check_task(self, parallel_results: list, run_id: str, **kwargs) -> dict:
    """Cross-check task entry point. Receives chord results."""
    self.worker_type = "cross_check"
    self._start_time = time.monotonic()
    return _run_async(_cross_check(run_id, parallel_results, self.update_progress))
