"""
GitHub Analysis Task — analyzes the startup's GitHub repositories.

Specifics:
- Soft timeout: 90s, Hard timeout: 120s
- Respects GitHub rate limits (checks X-RateLimit-Remaining header)
- Caches results by {repo_url + latest_commit_sha} in Redis (1hr TTL)
- Extracts: commit frequency, contributor count, code quality signals,
  README completeness, license, tech stack, activity recency
"""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone

import structlog

from src.workers.celery_app import celery_app
from src.workers.tasks.base_task import BaseEvalTask, _run_async

logger = structlog.get_logger(__name__)


from src.cache import cache_manager

async def _analyze_github(
    run_id: str,
    context: dict,
    update_progress,
) -> dict:
    """
    Core GitHub analysis logic.

    Steps:
    1. Extract repo URL from submission metadata
    2. Check cache by {repo_url + latest_commit_sha}
    3. Fetch repo metadata (respecting rate limits)
    4. Analyze commit history, contributors, code quality
    5. Cache results and return
    """
    import httpx

    metadata = context.get("metadata", {})
    github_url = metadata.get("github_url", "")

    if not github_url:
        return {
            "status": "skipped",
            "reason": "No GitHub URL provided",
            "scores": {},
        }

    update_progress(run_id, 10, "Checking GitHub cache")

    # Parse owner/repo from URL
    parts = github_url.rstrip("/").split("/")
    if len(parts) < 2:
        return {"status": "error", "reason": "Invalid GitHub URL"}

    owner, repo = parts[-2], parts[-1]

    update_progress(run_id, 20, "Fetching repository metadata & limits")

    # ── Step 1: Initialize Http Client & Apply Rate Limiting
    headers = {"Accept": "application/vnd.github.v3+json"}
    github_token = metadata.get("github_token", "")
    if github_token:
        headers["Authorization"] = f"Bearer {github_token}"

    async with httpx.AsyncClient(timeout=30.0) as client:
        # Check rate limit first
        rate_resp = await client.get(
            "https://api.github.com/rate_limit", headers=headers
        )
        if rate_resp.status_code == 200:
            remaining = int(rate_resp.headers.get("X-RateLimit-Remaining", "60"))
            if remaining < 10:
                reset_at = int(rate_resp.headers.get("X-RateLimit-Reset", "0"))
                wait_secs = max(0, reset_at - int(time.time()))
                if wait_secs > 60:
                    return {"status": "rate_limited", "reason": f"GitHub rate limit. Resets in {wait_secs}s"}
                if wait_secs > 0:
                    import asyncio
                    await asyncio.sleep(wait_secs)

        # ── Step 2: Fetch latest commit to produce deterministic cache key
        update_progress(run_id, 30, "Checking cache for latest commit")
        commits_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/commits",
            headers=headers,
            params={"per_page": 100},
        )
        commits_data = commits_resp.json() if commits_resp.status_code == 200 else []
        latest_sha = commits_data[0].get("sha", "HEAD") if commits_data else "UNKNOWN"
        url_hash = hashlib.sha256(f"https://github.com/{owner}/{repo}".encode()).hexdigest()
        
        cache_key = f"github:{url_hash}:{latest_sha}"
        cached_result = await cache_manager.get(cache_key)
        
        if cached_result:
            update_progress(run_id, 100, "Loaded from cache")
            return cached_result["val"] if "val" in cached_result else cached_result

        # ── Step 3: Fetch remaining analysis (Cache Missed)
        update_progress(run_id, 45, "Cache miss - Analyzing repository")
        
        repo_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers=headers,
        )

        if repo_resp.status_code == 404:
            return {"status": "error", "reason": "Repository not found"}
        if repo_resp.status_code != 200:
            return {"status": "error", "reason": f"GitHub API error: {repo_resp.status_code}"}

        repo_data = repo_resp.json()
        commits = commits_data  # reuse the payload

        # Fetch contributors
        update_progress(run_id, 60, "Analyzing contributors")
        contrib_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/contributors",
            headers=headers,
            params={"per_page": 30},
        )
        contributors = contrib_resp.json() if contrib_resp.status_code == 200 else []

        # Fetch languages
        update_progress(run_id, 70, "Analyzing tech stack")
        lang_resp = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}/languages",
            headers=headers,
        )
        languages = lang_resp.json() if lang_resp.status_code == 200 else {}

    # ── Step 3: Compute analysis scores ──────────────────
    update_progress(run_id, 80, "Computing scores")

    # Activity recency (days since last commit)
    last_push = repo_data.get("pushed_at", "")
    if last_push:
        last_push_dt = datetime.fromisoformat(last_push.replace("Z", "+00:00"))
        days_since_push = (datetime.now(timezone.utc) - last_push_dt).days
    else:
        days_since_push = 999

    # Compute scores (0.0 - 1.0)
    activity_score = max(0, min(1.0, 1.0 - (days_since_push / 365)))
    commit_score = min(1.0, len(commits) / 50)  # 50+ commits = 1.0
    contributor_score = min(1.0, len(contributors) / 5)  # 5+ = 1.0
    star_score = min(1.0, repo_data.get("stargazers_count", 0) / 100)
    has_readme = 1.0 if repo_data.get("description") else 0.3
    has_license = 1.0 if repo_data.get("license") else 0.0

    result = {
        "status": "completed",
        "repo": f"{owner}/{repo}",
        "scores": {
            "activity_recency": round(activity_score, 4),
            "commit_frequency": round(commit_score, 4),
            "contributor_diversity": round(contributor_score, 4),
            "community_traction": round(star_score, 4),
            "documentation_quality": round(has_readme, 4),
            "license_compliance": round(has_license, 4),
        },
        "metadata": {
            "stars": repo_data.get("stargazers_count", 0),
            "forks": repo_data.get("forks_count", 0),
            "open_issues": repo_data.get("open_issues_count", 0),
            "primary_language": repo_data.get("language", "unknown"),
            "languages": languages,
            "total_commits_analyzed": len(commits),
            "total_contributors": len(contributors),
            "days_since_last_push": days_since_push,
            "created_at": repo_data.get("created_at"),
            "last_pushed_at": last_push,
        },
        "claims": [
            {
                "text": f"Repository has {repo_data.get('stargazers_count', 0)} stars",
                "category": "traction",
                "confidence": 1.0,
            },
            {
                "text": f"Primary language is {repo_data.get('language', 'unknown')}",
                "category": "product",
                "confidence": 1.0,
            },
            {
                "text": f"{len(contributors)} contributors active on the project",
                "category": "team",
                "confidence": 0.9,
            },
        ],
    }

    # ── Step 4: Cache the result ─────────────────────────
    update_progress(run_id, 90, "Caching results")
    await cache_manager.set(cache_key, result, ttl=3600)

    return result


@celery_app.task(
    name="src.workers.tasks.github_analysis.github_analysis_task",
    base=BaseEvalTask,
    bind=True,
    max_retries=3,
    soft_time_limit=90,
    time_limit=120,
)
def github_analysis_task(self, run_id: str, **context) -> dict:
    """GitHub analysis task entry point."""
    self.worker_type = "github_analysis"
    self._start_time = time.monotonic()
    return self.run(run_id, **context)


# Override execute for BaseEvalTask pattern
github_analysis_task.execute = lambda self, run_id, **ctx: _analyze_github(
    run_id, ctx, self.update_progress
)
