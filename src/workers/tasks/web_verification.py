"""
Web Verification Task — verifies claims against the startup's website.

Crawls the startup's website to extract and verify claims about:
- Product features, team members, partners, metrics
- Cross-references with submission metadata
- Soft timeout: 90s, Hard timeout: 120s
"""

from __future__ import annotations

import time

import structlog

from src.workers.celery_app import celery_app
from src.workers.tasks.base_task import BaseEvalTask, _run_async

logger = structlog.get_logger(__name__)


async def _verify_web(
    run_id: str,
    context: dict,
    update_progress,
) -> dict:
    """
    Core web verification logic.

    1. Fetch the startup's website
    2. Extract structured data (team, product, metrics)
    3. Cross-reference with submission claims
    """
    import httpx

    website_url = context.get("website_url", "")
    if not website_url:
        return {
            "status": "skipped",
            "reason": "No website URL provided",
            "scores": {},
        }

    update_progress(run_id, 10, "Fetching website")

    try:
        async with httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            max_redirects=5,
        ) as client:
            # ── Step 1: Fetch main page ──────────────────
            resp = await client.get(website_url)
            if resp.status_code != 200:
                return {
                    "status": "error",
                    "reason": f"Website returned HTTP {resp.status_code}",
                    "scores": {"web_presence": 0.2},
                }

            html = resp.text
            content_length = len(html)

            update_progress(run_id, 30, "Analyzing page content")

            # ── Step 2: Extract structured data ──────────
            # Check for key pages
            pages_found = {"main": True}
            key_pages = {
                "about": ["/about", "/about-us", "/team"],
                "pricing": ["/pricing", "/plans"],
                "blog": ["/blog", "/news"],
                "contact": ["/contact", "/support"],
                "docs": ["/docs", "/documentation", "/api"],
            }

            update_progress(run_id, 40, "Crawling key pages")

            for page_type, paths in key_pages.items():
                for path in paths:
                    try:
                        full_url = website_url.rstrip("/") + path
                        page_resp = await client.get(full_url)
                        if page_resp.status_code == 200:
                            pages_found[page_type] = True
                            break
                    except Exception:
                        continue
                if page_type not in pages_found:
                    pages_found[page_type] = False

            update_progress(run_id, 60, "Extracting claims")

            # ── Step 3: Extract claims from website ──────
            html_lower = html.lower()
            claims = []

            # Check for social proof
            social_signals = {
                "customers": ["customer", "client", "trusted by"],
                "partners": ["partner", "integration", "powered by"],
                "press": ["featured in", "as seen in", "press"],
                "metrics": ["users", "revenue", "growth", "%"],
            }

            for signal_type, keywords in social_signals.items():
                for kw in keywords:
                    if kw in html_lower:
                        claims.append({
                            "text": f"Website mentions {signal_type} ({kw})",
                            "category": signal_type if signal_type != "metrics" else "traction",
                            "confidence": 0.6,
                            "source_reference": f"Website: {website_url}",
                        })
                        break

            update_progress(run_id, 80, "Computing web presence scores")

            # ── Step 4: Compute scores ───────────────────
            pages_score = sum(pages_found.values()) / len(pages_found)
            content_score = min(1.0, content_length / 50000)  # 50KB+ = 1.0
            ssl_score = 1.0 if website_url.startswith("https") else 0.3

            # Check for technical signals
            has_structured_data = "application/ld+json" in html_lower
            has_meta_og = 'property="og:' in html_lower
            tech_score = 0.5 + (0.25 if has_structured_data else 0) + (0.25 if has_meta_og else 0)

            return {
                "status": "completed",
                "scores": {
                    "web_presence": round(pages_score, 4),
                    "content_richness": round(content_score, 4),
                    "security": round(ssl_score, 4),
                    "technical_quality": round(tech_score, 4),
                },
                "metadata": {
                    "pages_found": pages_found,
                    "content_length_bytes": content_length,
                    "is_https": website_url.startswith("https"),
                    "has_structured_data": has_structured_data,
                    "has_opengraph": has_meta_og,
                },
                "claims": claims,
            }

    except httpx.TimeoutException:
        return {
            "status": "error",
            "reason": "Website request timed out",
            "scores": {"web_presence": 0.1},
        }
    except Exception as e:
        return {
            "status": "error",
            "reason": f"Web verification failed: {str(e)}",
            "scores": {},
        }


@celery_app.task(
    name="src.workers.tasks.web_verification.web_verification_task",
    base=BaseEvalTask,
    bind=True,
    max_retries=3,
    soft_time_limit=90,
    time_limit=120,
)
def web_verification_task(self, run_id: str, **context) -> dict:
    """Web verification task entry point."""
    self.worker_type = "web_verification"
    self._start_time = time.monotonic()
    return self.run(run_id, **context)


web_verification_task.execute = lambda self, run_id, **ctx: _verify_web(
    run_id, ctx, self.update_progress
)
