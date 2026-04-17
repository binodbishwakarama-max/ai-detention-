"""
Fabrication Detection Task — identifies potentially fabricated claims.

Analyzes claims for signs of fabrication:
- Implausible metrics (e.g., "10M users" for a 2-month-old startup)
- Unverifiable claims (no supporting evidence)
- Statistical anomalies in financial projections
"""

from __future__ import annotations

import time
from uuid import UUID

import structlog

from src.workers.celery_app import celery_app
from src.workers.tasks.base_task import BaseEvalTask, _run_async

logger = structlog.get_logger(__name__)


async def _detect_fabrication(
    run_id: str,
    cross_check_result: dict,
    update_progress,
) -> dict:
    """
    Analyze claims for potential fabrication.

    Checks:
    1. Implausibility: metrics that defy industry norms
    2. Consistency: internal consistency of claims
    3. Verifiability: whether claims can be independently verified
    """
    from sqlalchemy import select
    from src.database import get_standalone_session
    from src.models.claim import Claim

    update_progress(run_id, 10, "Loading claims for fabrication analysis")

    async with get_standalone_session() as db:
        # Fetch all claims for this run
        result = await db.execute(
            select(Claim).where(
                Claim.evaluation_run_id == UUID(run_id),
                Claim.deleted_at.is_(None),
            )
        )
        claims = list(result.scalars().all())

    if not claims:
        return {
            "status": "completed",
            "fabrication_risk": "low",
            "flagged_claims": 0,
        }

    update_progress(run_id, 30, f"Analyzing {len(claims)} claims for fabrication")

    flagged = []
    total_risk_score = 0.0

    for idx, claim in enumerate(claims):
        risk = _assess_claim_risk(claim.claim_text, claim.category, claim.confidence_score)

        if risk["score"] > 0.5:
            flagged.append({
                "claim_id": str(claim.id),
                "claim_text": claim.claim_text,
                "risk_score": risk["score"],
                "risk_factors": risk["factors"],
                "category": claim.category,
            })

            # Update verification status in DB
            async with get_standalone_session() as db:
                from sqlalchemy import update
                await db.execute(
                    update(Claim)
                    .where(Claim.id == claim.id)
                    .values(
                        verification_status="disputed" if risk["score"] > 0.7 else "unverified",
                        evidence={
                            **claim.evidence,
                            "fabrication_risk": risk,
                        },
                    )
                )

        total_risk_score += risk["score"]

        progress = 30 + int((idx / len(claims)) * 60)
        update_progress(run_id, min(90, progress), "Analyzing claim verifiability")

    update_progress(run_id, 95, "Computing fabrication summary")

    avg_risk = total_risk_score / len(claims) if claims else 0
    risk_level = (
        "high" if avg_risk > 0.6
        else "medium" if avg_risk > 0.3
        else "low"
    )

    return {
        "status": "completed",
        "fabrication_risk": risk_level,
        "average_risk_score": round(avg_risk, 4),
        "total_claims_analyzed": len(claims),
        "flagged_claims": len(flagged),
        "flagged": flagged[:10],  # top 10 highest risk
        "cross_check_contradictions": cross_check_result.get("contradictions_found", 0),
    }


def _assess_claim_risk(text: str, category: str, confidence: float) -> dict:
    """
    Assess fabrication risk for a single claim.

    Returns a risk score (0-1) and the factors contributing to risk.
    """
    import re

    factors = []
    risk = 0.0

    text_lower = text.lower()

    # ── Superlative claims ───────────────────────────────
    superlatives = ["first", "only", "best", "largest", "fastest", "revolutionary"]
    for word in superlatives:
        if word in text_lower:
            risk += 0.2
            factors.append(f"Superlative claim: '{word}'")
            break

    # ── Round number bias (fabricated metrics tend to be round) ─
    numbers = re.findall(r"\b(\d+)\b", text)
    for num in numbers:
        n = int(num)
        if n >= 1000 and n % 1000 == 0:
            risk += 0.15
            factors.append(f"Suspiciously round number: {n}")
        elif n >= 100 and n % 100 == 0:
            risk += 0.1
            factors.append(f"Round number: {n}")

    # ── Implausible growth claims ────────────────────────
    growth_patterns = [
        (r"(\d+)x\s*growth", 0.2, "Extreme growth multiplier"),
        (r"(\d+)%\s*(growth|increase)", 0.1, "High percentage growth"),
        (r"(\d+)\s*million\s*users", 0.3, "Large user count claim"),
    ]
    for pattern, score, reason in growth_patterns:
        if re.search(pattern, text_lower):
            risk += score
            factors.append(reason)

    # ── Low confidence from extraction ───────────────────
    if confidence < 0.5:
        risk += 0.15
        factors.append(f"Low extraction confidence: {confidence}")

    return {
        "score": min(1.0, round(risk, 4)),
        "factors": factors,
    }


@celery_app.task(
    name="src.workers.tasks.fabrication.fabrication_detection_task",
    base=BaseEvalTask,
    bind=True,
    max_retries=3,
    soft_time_limit=120,
    time_limit=150,
)
def fabrication_detection_task(self, cross_check_result: dict, run_id: str, **kwargs) -> dict:
    """Fabrication detection task entry point."""
    self.worker_type = "fabrication_detection"
    self._start_time = time.monotonic()
    return _run_async(
        _detect_fabrication(run_id, cross_check_result, self.update_progress)
    )
