"""
LLM Judge Task — AI-powered scoring with structured output.

Specifics:
- Structured output with JSON schema validation (Pydantic)
- Fallback: if primary model fails, retry with backup model
- Cost tracking: log token usage to DB for billing
- Produces scores for each evaluation dimension
- Soft timeout: 180s, Hard timeout: 240s
"""

from __future__ import annotations

import hashlib
import json
import time
from uuid import UUID

import structlog

from src.cache import cached
from src.workers.celery_app import celery_app
from src.workers.tasks.base_task import BaseEvalTask, _run_async

logger = structlog.get_logger(__name__)

# ── JSON Schema for LLM Structured Output ───────────────────
LLM_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["scores", "overall_assessment", "key_strengths", "key_risks"],
    "properties": {
        "scores": {
            "type": "object",
            "required": [
                "market_opportunity", "team_strength", "product_viability",
                "financial_health", "traction", "overall",
            ],
            "properties": {
                "market_opportunity": {"type": "object", "properties": {
                    "value": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                }},
                "team_strength": {"type": "object", "properties": {
                    "value": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                }},
                "product_viability": {"type": "object", "properties": {
                    "value": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                }},
                "financial_health": {"type": "object", "properties": {
                    "value": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                }},
                "traction": {"type": "object", "properties": {
                    "value": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                }},
                "overall": {"type": "object", "properties": {
                    "value": {"type": "number", "minimum": 0, "maximum": 1},
                    "rationale": {"type": "string"},
                }},
            },
        },
        "overall_assessment": {"type": "string"},
        "key_strengths": {"type": "array", "items": {"type": "string"}},
        "key_risks": {"type": "array", "items": {"type": "string"}},
    },
}

# Model configuration
PRIMARY_MODEL = "gpt-4-turbo"
BACKUP_MODEL = "gpt-3.5-turbo"

# Dimension weights
DIMENSION_WEIGHTS = {
    "market_opportunity": 0.2,
    "team_strength": 0.2,
    "product_viability": 0.2,
    "financial_health": 0.15,
    "traction": 0.15,
    "overall": 0.1,
}


async def _run_llm_judge(
    run_id: str,
    fabrication_result: dict,
    update_progress,
) -> dict:
    """
    Execute LLM-based scoring with fallback and cost tracking.

    1. Build prompt from all previous task results
    2. Call primary model (GPT-4-turbo)
    3. Validate structured output against JSON schema
    4. On failure: fallback to backup model (GPT-3.5-turbo)
    5. Store scores and log token usage for billing
    """
    from sqlalchemy import select
    from src.database import get_standalone_session
    from src.models.claim import Claim
    from src.models.contradiction import Contradiction
    from src.models.score import Score
    from src.models.evaluation import EvaluationRun
    from src.models.worker_result import WorkerResult

    update_progress(run_id, 10, "Building evaluation context")

    # ── Step 1: Gather all analysis results ──────────────
    async with get_standalone_session() as db:
        # Get claims
        claims_result = await db.execute(
            select(Claim).where(
                Claim.evaluation_run_id == UUID(run_id),
                Claim.deleted_at.is_(None),
            )
        )
        claims = list(claims_result.scalars().all())

        # Get contradictions
        contradict_result = await db.execute(
            select(Contradiction).where(
                Contradiction.evaluation_run_id == UUID(run_id),
                Contradiction.deleted_at.is_(None),
            )
        )
        contradictions = list(contradict_result.scalars().all())

        # Get worker results for context
        wr_result = await db.execute(
            select(WorkerResult).where(
                WorkerResult.evaluation_run_id == UUID(run_id),
                WorkerResult.deleted_at.is_(None),
            )
        )
        worker_results = list(wr_result.scalars().all())

        # Get run for org_id
        run_result = await db.execute(
            select(EvaluationRun).where(EvaluationRun.id == UUID(run_id))
        )
        run = run_result.scalar_one()

    update_progress(run_id, 20, "Constructing LLM prompt")

    # ── Step 2: Build prompt ─────────────────────────────
    claims_text = "\n".join(
        f"- [{c.category}] {c.claim_text} (confidence: {c.confidence_score})"
        for c in claims[:50]  # limit to 50 claims
    )
    contradictions_text = "\n".join(
        f"- {c.explanation} (severity: {c.severity})"
        for c in contradictions[:20]
    )
    fabrication_summary = (
        f"Fabrication risk: {fabrication_result.get('fabrication_risk', 'unknown')}\n"
        f"Flagged claims: {fabrication_result.get('flagged_claims', 0)}"
    )

    prompt = f"""You are an expert startup evaluator. Analyze the following data and provide scores.

EXTRACTED CLAIMS:
{claims_text or "No claims extracted."}

DETECTED CONTRADICTIONS:
{contradictions_text or "No contradictions detected."}

FABRICATION ANALYSIS:
{fabrication_summary}

Score each dimension from 0.0 to 1.0 with a rationale.
Respond with valid JSON matching the required schema."""

    update_progress(run_id, 40, "Calling primary LLM model")

    # ── Step 3: Call LLM with fallback ───────────────────
    llm_output = None
    token_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    model_used = PRIMARY_MODEL

    try:
        llm_output, usage = await _call_llm(prompt, PRIMARY_MODEL)
        token_usage = usage
    except Exception as primary_err:
        logger.warning(
            "llm_judge.primary_model_failed",
            error=str(primary_err),
            model=PRIMARY_MODEL,
        )
        update_progress(run_id, 50, "Primary model failed, trying backup")

        try:
            llm_output, usage = await _call_llm(prompt, BACKUP_MODEL)
            token_usage = usage
            model_used = BACKUP_MODEL
        except Exception as backup_err:
            logger.error(
                "llm_judge.both_models_failed",
                primary_error=str(primary_err),
                backup_error=str(backup_err),
            )
            # Return synthetic scores based on available data
            llm_output = _generate_synthetic_scores(claims, contradictions, fabrication_result)
            model_used = "synthetic"

    update_progress(run_id, 70, "Validating LLM output")

    # ── Step 4: Validate structured output ───────────────
    validated = _validate_llm_output(llm_output)
    if not validated:
        validated = _generate_synthetic_scores(claims, contradictions, fabrication_result)
        model_used = f"{model_used}_fallback"

    update_progress(run_id, 80, "Storing scores in database")

    # ── Step 5: Store immutable scores in DB ─────────────
    async with get_standalone_session() as db:
        for dimension, weight in DIMENSION_WEIGHTS.items():
            dim_data = validated["scores"].get(dimension, {})
            score = Score(
                evaluation_run_id=UUID(run_id),
                organization_id=run.organization_id,
                dimension=dimension,
                value=dim_data.get("value", 0.5),
                weight=weight,
                rationale=dim_data.get("rationale", ""),
                breakdown={
                    "model_used": model_used,
                    "token_usage": token_usage,
                },
            )
            db.add(score)

        await db.flush()

    update_progress(run_id, 90, "Logging token usage for billing")

    # ── Step 6: Log token usage for billing ──────────────
    from src.repositories.audit_log_repository import audit_log_repo
    from src.models.audit_log import AuditAction

    async with get_standalone_session() as db:
        await audit_log_repo.create(
            db,
            action=AuditAction.SCORE_RECORDED,
            resource_type="evaluation_run",
            resource_id=run_id,
            organization_id=run.organization_id,
            changes={
                "model_used": model_used,
                "token_usage": token_usage,
                "estimated_cost_usd": _estimate_cost(token_usage, model_used),
            },
        )

    # ── Record LLM observability metrics ──────────────
    try:
        from src.observability.metrics import get_metrics

        metrics = get_metrics()
        metrics.llm_tokens_used_total.labels(
            model=model_used, task_type="llm_judge"
        ).inc(token_usage.get("total_tokens", 0))
        metrics.llm_cost_usd_total.labels(
            model=model_used, task_type="llm_judge"
        ).inc(_estimate_cost(token_usage, model_used))
    except Exception:
        pass  # Metrics unavailable — fail open

    return {
        "status": "completed",
        "model_used": model_used,
        "token_usage": token_usage,
        "estimated_cost_usd": _estimate_cost(token_usage, model_used),
        "scores": validated["scores"],
        "overall_assessment": validated.get("overall_assessment", ""),
        "key_strengths": validated.get("key_strengths", []),
        "key_risks": validated.get("key_risks", []),
    }


def llm_cache_key(prompt: str, model: str) -> str:
    prompt_hash = hashlib.sha256(prompt.encode()).hexdigest()
    return f"llm:{prompt_hash}:{model}"


@cached(ttl=86400, key_builder=llm_cache_key)
async def _call_llm(prompt: str, model: str) -> tuple[dict, dict]:
    """
    Call the LLM API and return parsed JSON + token usage.

    In production: use the OpenAI/Anthropic client.
    Here we simulate to avoid external dependencies.
    """
    import httpx

    # Simulated LLM response for demonstration
    # In production, replace with actual API call:
    # response = await openai_client.chat.completions.create(...)
    simulated_response = {
        "scores": {
            "market_opportunity": {"value": 0.72, "rationale": "Large addressable market with growing demand"},
            "team_strength": {"value": 0.65, "rationale": "Experienced founders with relevant domain expertise"},
            "product_viability": {"value": 0.78, "rationale": "Strong technical foundation with clear differentiation"},
            "financial_health": {"value": 0.55, "rationale": "Early stage with limited revenue data"},
            "traction": {"value": 0.60, "rationale": "Moderate user growth with positive engagement metrics"},
            "overall": {"value": 0.68, "rationale": "Promising startup with room for growth"},
        },
        "overall_assessment": "A promising early-stage startup with strong technical foundations.",
        "key_strengths": ["Strong product differentiation", "Experienced technical team"],
        "key_risks": ["Limited revenue traction", "Competitive market landscape"],
    }

    usage = {
        "prompt_tokens": len(prompt.split()) * 2,  # rough estimate
        "completion_tokens": 500,
        "total_tokens": len(prompt.split()) * 2 + 500,
    }

    return simulated_response, usage


def _validate_llm_output(output: dict) -> dict | None:
    """Validate LLM output against the expected JSON schema."""
    try:
        if not isinstance(output, dict):
            return None
        if "scores" not in output:
            return None

        scores = output["scores"]
        for dim in DIMENSION_WEIGHTS:
            if dim not in scores:
                return None
            dim_data = scores[dim]
            if not isinstance(dim_data, dict) or "value" not in dim_data:
                return None
            value = dim_data["value"]
            if not isinstance(value, (int, float)) or value < 0 or value > 1:
                return None

        return output
    except Exception:
        return None


def _generate_synthetic_scores(
    claims: list, contradictions: list, fabrication_result: dict
) -> dict:
    """Generate scores from available data when LLM is unavailable."""
    # Base score from claim quality
    avg_confidence = (
        sum(c.confidence_score for c in claims) / len(claims)
        if claims else 0.5
    )

    # Penalty for contradictions
    contradiction_penalty = min(0.3, len(contradictions) * 0.05)

    # Penalty for fabrication
    fab_risk = fabrication_result.get("average_risk_score", 0)
    fab_penalty = fab_risk * 0.2

    base_score = max(0.1, avg_confidence - contradiction_penalty - fab_penalty)

    scores = {}
    for dim in DIMENSION_WEIGHTS:
        import random
        variation = random.uniform(-0.1, 0.1)
        scores[dim] = {
            "value": round(max(0, min(1, base_score + variation)), 4),
            "rationale": f"Synthetic score based on {len(claims)} claims",
        }

    return {
        "scores": scores,
        "overall_assessment": "Score generated from analytical data (LLM unavailable)",
        "key_strengths": [],
        "key_risks": ["LLM evaluation unavailable — synthetic scores used"],
    }


def _estimate_cost(usage: dict, model: str) -> float:
    """Estimate API cost in USD based on token usage."""
    rates = {
        "gpt-4-turbo": {"prompt": 0.01 / 1000, "completion": 0.03 / 1000},
        "gpt-3.5-turbo": {"prompt": 0.0005 / 1000, "completion": 0.0015 / 1000},
        "synthetic": {"prompt": 0, "completion": 0},
    }
    rate = rates.get(model, rates["gpt-3.5-turbo"])
    cost = (
        usage.get("prompt_tokens", 0) * rate["prompt"]
        + usage.get("completion_tokens", 0) * rate["completion"]
    )
    return round(cost, 6)


@celery_app.task(
    name="src.workers.tasks.llm_judge.llm_judge_task",
    base=BaseEvalTask,
    bind=True,
    max_retries=3,
    soft_time_limit=180,
    time_limit=240,
)
def llm_judge_task(self, fabrication_result: dict, run_id: str, **kwargs) -> dict:
    """LLM Judge task entry point."""
    self.worker_type = "llm_judge"
    self._start_time = time.monotonic()
    return _run_async(
        _run_llm_judge(run_id, fabrication_result, self.update_progress)
    )
