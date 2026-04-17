"""
Seed demo data via the REST API for a compelling hackathon demo.
Creates a user, submissions, evaluation configs, and evaluation runs.
"""

import asyncio
import random
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import text


async def seed():
    # Import inside function to avoid module-level side effects
    from src.database import get_session_factory, init_engine
    from src.models.evaluation import EvaluationConfig, EvaluationRun, RunStatus
    from src.models.organization import Organization
    from src.models.submission import Submission, SubmissionStatus
    from src.models.user import User
    from src.security import Role, hash_password

    await init_engine()
    factory = get_session_factory()

    async with factory() as db:
        try:
            # ── 1. Create Organization ──────────────────────────────
            org = Organization(name="TechVenture Capital", slug="techventure-capital")
            db.add(org)
            await db.flush()

            # ── 2. Create Admin User ────────────────────────────────
            user = User(
                email="admin@techventure.ai",
                hashed_password=hash_password("demo1234"),
                full_name="Demo Admin",
                role=Role.ADMIN,
                organization_id=org.id,
                is_active=True,
            )
            db.add(user)
            await db.flush()

            print(f"✅ Created org: {org.name} ({org.id})")
            print(f"✅ Created user: {user.email} ({user.id})")

            # ── 3. Create Startup Submissions ───────────────────────
            startups = [
                {
                    "startup_name": "NeuraScan AI",
                    "description": "AI-powered medical imaging diagnostics that detects early-stage cancers with 97% accuracy using proprietary transformer models.",
                    "website_url": "https://neurascan.ai",
                    "status": SubmissionStatus.EVALUATED,
                    "metadata_": {"sector": "HealthTech", "funding_stage": "Series A", "team_size": 24, "mrr": 180000},
                },
                {
                    "startup_name": "QuantumLedger",
                    "description": "Post-quantum cryptographic protocols for enterprise blockchain. First in the market to achieve NIST PQC certification.",
                    "website_url": "https://quantumledger.io",
                    "status": SubmissionStatus.EVALUATED,
                    "metadata_": {"sector": "Web3 + Security", "funding_stage": "Series B", "team_size": 42, "mrr": 520000},
                },
                {
                    "startup_name": "GreenGrid Energy",
                    "description": "AI-optimized smart grid management reducing energy waste by 35% for municipal utilities using real-time demand prediction.",
                    "website_url": "https://greengrid.energy",
                    "status": SubmissionStatus.EVALUATED,
                    "metadata_": {"sector": "CleanTech", "funding_stage": "Seed", "team_size": 11, "mrr": 45000},
                },
                {
                    "startup_name": "DeepForge Robotics",
                    "description": "Autonomous warehouse robots with advanced SLAM navigation. Deployed in 120+ fulfillment centers across North America.",
                    "website_url": "https://deepforge.bot",
                    "status": SubmissionStatus.UNDER_REVIEW,
                    "metadata_": {"sector": "Robotics", "funding_stage": "Series A", "team_size": 35, "mrr": 290000},
                },
                {
                    "startup_name": "VoiceOS",
                    "description": "Enterprise voice AI platform enabling natural language workflows across CRM, ERP, and custom business applications.",
                    "website_url": "https://voiceos.dev",
                    "status": SubmissionStatus.SUBMITTED,
                    "metadata_": {"sector": "Enterprise SaaS", "funding_stage": "Pre-Seed", "team_size": 6, "mrr": 12000},
                },
                {
                    "startup_name": "BioSynth Labs",
                    "description": "Computational protein design platform leveraging generative AI for rapid drug discovery. 3 compounds in Phase I trials.",
                    "website_url": "https://biosynth.labs",
                    "status": SubmissionStatus.EVALUATED,
                    "metadata_": {"sector": "BioTech", "funding_stage": "Series C", "team_size": 78, "mrr": 0},
                },
                {
                    "startup_name": "Orbitas Space",
                    "description": "Low-cost satellite constellation for global IoT connectivity. 40 satellites launched, targeting 200 by 2027.",
                    "website_url": "https://orbitas.space",
                    "status": SubmissionStatus.EVALUATED,
                    "metadata_": {"sector": "SpaceTech", "funding_stage": "Series B", "team_size": 55, "mrr": 340000},
                },
                {
                    "startup_name": "EduVerse AI",
                    "description": "Personalized AI tutoring platform adapting to individual student learning patterns. Used by 2M+ students across 15 countries.",
                    "website_url": "https://eduverse.ai",
                    "status": SubmissionStatus.SUBMITTED,
                    "metadata_": {"sector": "EdTech", "funding_stage": "Series A", "team_size": 28, "mrr": 95000},
                },
            ]

            submissions = []
            for i, s_data in enumerate(startups):
                sub = Submission(
                    startup_name=s_data["startup_name"],
                    description=s_data["description"],
                    website_url=s_data["website_url"],
                    status=s_data["status"],
                    metadata_=s_data["metadata_"],
                    organization_id=org.id,
                    submitted_by_id=user.id,
                    created_at=datetime.now(timezone.utc) - timedelta(days=random.randint(1, 14), hours=random.randint(0, 23)),
                )
                db.add(sub)
                await db.flush()
                submissions.append(sub)
                print(f"  📋 Submission: {sub.startup_name} ({sub.status.value})")

            # ── 4. Create Evaluation Configs ────────────────────────
            configs_data = [
                {
                    "name": "Full Due Diligence Pipeline",
                    "description": "Comprehensive 7-stage evaluation: GitHub analysis, pitch deck review, web verification, cross-referencing, fabrication detection, LLM judging, and final scoring.",
                    "pipeline_config": {
                        "steps": ["github_analysis", "pitch_deck", "web_verification", "video_analysis", "cross_check", "fabrication_detection", "llm_judge"],
                        "weights": {"github": 0.15, "pitch_deck": 0.20, "web": 0.10, "video": 0.10, "cross_check": 0.15, "fabrication": 0.15, "llm_judge": 0.15},
                        "model": "gemini-2.5-pro",
                        "max_retries": 3,
                    },
                    "is_template": True,
                    "version": 3,
                },
                {
                    "name": "Quick Screening",
                    "description": "Fast 3-stage screening: web verification, pitch analysis, and AI judgment. Completes in under 2 minutes.",
                    "pipeline_config": {
                        "steps": ["web_verification", "pitch_deck", "llm_judge"],
                        "weights": {"web": 0.30, "pitch_deck": 0.35, "llm_judge": 0.35},
                        "model": "gemini-2.5-flash",
                        "max_retries": 2,
                    },
                    "is_template": True,
                    "version": 2,
                },
                {
                    "name": "Technical Deep Dive",
                    "description": "Engineering-focused evaluation: GitHub repository analysis, code quality assessment, and architecture review.",
                    "pipeline_config": {
                        "steps": ["github_analysis", "cross_check", "llm_judge"],
                        "weights": {"github": 0.45, "cross_check": 0.25, "llm_judge": 0.30},
                        "model": "gemini-2.5-pro",
                        "max_retries": 3,
                    },
                    "is_template": True,
                    "version": 1,
                },
            ]

            configs = []
            for c_data in configs_data:
                config = EvaluationConfig(
                    name=c_data["name"],
                    description=c_data["description"],
                    pipeline_config=c_data["pipeline_config"],
                    is_template=c_data["is_template"],
                    version=c_data["version"],
                    organization_id=org.id,
                    created_by_id=user.id,
                )
                db.add(config)
                await db.flush()
                configs.append(config)
                print(f"  ⚙️  Config: {config.name} (v{config.version})")

            # ── 5. Create Evaluation Runs ───────────────────────────
            run_data = [
                # Completed runs with scores
                {"sub_idx": 0, "cfg_idx": 0, "status": RunStatus.COMPLETED, "score": 0.87, "workers": 7, "completed": 7, "failed": 0, "days_ago": 1},
                {"sub_idx": 1, "cfg_idx": 0, "status": RunStatus.COMPLETED, "score": 0.92, "workers": 7, "completed": 7, "failed": 0, "days_ago": 2},
                {"sub_idx": 2, "cfg_idx": 1, "status": RunStatus.COMPLETED, "score": 0.74, "workers": 3, "completed": 3, "failed": 0, "days_ago": 3},
                {"sub_idx": 5, "cfg_idx": 0, "status": RunStatus.COMPLETED, "score": 0.95, "workers": 7, "completed": 7, "failed": 0, "days_ago": 1},
                {"sub_idx": 6, "cfg_idx": 2, "status": RunStatus.COMPLETED, "score": 0.81, "workers": 3, "completed": 3, "failed": 0, "days_ago": 4},
                {"sub_idx": 0, "cfg_idx": 1, "status": RunStatus.COMPLETED, "score": 0.89, "workers": 3, "completed": 3, "failed": 0, "days_ago": 5},
                {"sub_idx": 1, "cfg_idx": 2, "status": RunStatus.COMPLETED, "score": 0.91, "workers": 3, "completed": 3, "failed": 0, "days_ago": 6},
                {"sub_idx": 2, "cfg_idx": 0, "status": RunStatus.COMPLETED, "score": 0.72, "workers": 7, "completed": 7, "failed": 0, "days_ago": 7},
                # Running
                {"sub_idx": 3, "cfg_idx": 0, "status": RunStatus.RUNNING, "score": None, "workers": 7, "completed": 4, "failed": 0, "days_ago": 0},
                # Pending
                {"sub_idx": 4, "cfg_idx": 1, "status": RunStatus.PENDING, "score": None, "workers": 3, "completed": 0, "failed": 0, "days_ago": 0},
                # Failed
                {"sub_idx": 6, "cfg_idx": 0, "status": RunStatus.FAILED, "score": None, "workers": 7, "completed": 5, "failed": 2, "days_ago": 3, "error": "Worker timeout on video_analysis (exceeded 300s limit)"},
                # Another completed
                {"sub_idx": 5, "cfg_idx": 1, "status": RunStatus.COMPLETED, "score": 0.96, "workers": 3, "completed": 3, "failed": 0, "days_ago": 2},
            ]

            for rd in run_data:
                now = datetime.now(timezone.utc)
                created = now - timedelta(days=rd["days_ago"], hours=random.randint(0, 12))
                started = created + timedelta(seconds=random.randint(1, 10)) if rd["status"] != RunStatus.PENDING else None
                completed_at = started + timedelta(minutes=random.randint(1, 8)) if rd["status"] == RunStatus.COMPLETED else None

                progress = 100.0 if rd["status"] == RunStatus.COMPLETED else (
                    round(rd["completed"] / max(rd["workers"], 1) * 100, 1) if rd["status"] == RunStatus.RUNNING else 0.0
                )

                run = EvaluationRun(
                    submission_id=submissions[rd["sub_idx"]].id,
                    config_id=configs[rd["cfg_idx"]].id,
                    organization_id=org.id,
                    triggered_by_id=user.id,
                    status=rd["status"],
                    started_at=started,
                    completed_at=completed_at,
                    total_workers=rd["workers"],
                    completed_workers=rd["completed"],
                    failed_workers=rd["failed"],
                    overall_score=rd["score"],
                    error_message=rd.get("error"),
                    config_snapshot=configs[rd["cfg_idx"]].pipeline_config,
                    run_metadata={"source": "demo_seed", "version": "1.0"},
                    created_at=created,
                )
                db.add(run)
                status_str = rd["status"].value
                score_str = f" → {rd['score']*100:.0f}%" if rd["score"] else ""
                print(f"  🔬 Run: {startups[rd['sub_idx']]['startup_name']} [{status_str}]{score_str}")

            await db.commit()
            print("\n🎉 Demo data seeded successfully!")
            print(f"\n  Login: admin@techventure.ai / demo1234")
            print(f"  Dashboard: http://localhost:3001")
            print(f"  API Docs: http://localhost:8000/docs")

        except Exception as e:
            await db.rollback()
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()
            raise


if __name__ == "__main__":
    asyncio.run(seed())
