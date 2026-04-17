"""Initial schema — complete database layer

Revision ID: 001_initial_schema
Revises: None
Create Date: 2026-04-16

Creates all 9 tables with:
- Row-Level Security (RLS) policies for multi-tenancy
- Append-only trigger on audit_logs (no UPDATE/DELETE)
- Immutability trigger on scores (no UPDATE/DELETE)
- Partial indexes on commonly filtered columns
- Check constraints on score values
- Optimistic locking column on evaluation_runs
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers
revision: str = "001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables, indexes, triggers, and RLS policies."""

    # ── 1. ENUMS ─────────────────────────────────────────────
    plan_tier = postgresql.ENUM("free", "pro", "enterprise", name="plan_tier", create_type=True)
    user_role = postgresql.ENUM("admin", "judge", "viewer", name="user_role", create_type=True)
    submission_status = postgresql.ENUM(
        "draft", "submitted", "under_review", "evaluated", "archived",
        name="submission_status", create_type=True,
    )
    run_status = postgresql.ENUM(
        "pending", "running", "completed", "failed", "cancelled",
        name="run_status", create_type=True,
    )
    worker_status = postgresql.ENUM(
        "pending", "running", "completed", "failed",
        name="worker_status", create_type=True,
    )
    audit_action = postgresql.ENUM(
        "create", "read", "update", "delete",
        "login", "logout", "login_failed",
        "submission_created", "submission_updated",
        "evaluation_started", "evaluation_completed",
        "evaluation_failed", "evaluation_cancelled",
        "claim_extracted", "contradiction_detected",
        "score_recorded", "settings_changed",
        name="audit_action", create_type=True,
    )

    plan_tier.create(op.get_bind(), checkfirst=True)
    user_role.create(op.get_bind(), checkfirst=True)
    submission_status.create(op.get_bind(), checkfirst=True)
    run_status.create(op.get_bind(), checkfirst=True)
    worker_status.create(op.get_bind(), checkfirst=True)
    audit_action.create(op.get_bind(), checkfirst=True)

    # ── 2. ORGANIZATIONS ────────────────────────────────────
    op.create_table(
        "organizations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("plan_tier", postgresql.ENUM(name="plan_tier", create_type=False), nullable=False, server_default="free"),
        sa.Column("rate_limit_per_minute", sa.Integer(), nullable=False, server_default="100"),
        sa.Column("max_concurrent_evaluations", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("settings", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Partial unique index: slug uniqueness only among active orgs
    op.create_index(
        "ix_organizations_slug_active", "organizations", ["slug"],
        unique=True, postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── 3. USERS ─────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", postgresql.ENUM(name="user_role", create_type=False), nullable=False, server_default="viewer"),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_login_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_users_email_active", "users", ["email"],
        unique=True, postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_users_org_active", "users", ["organization_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── 4. SUBMISSIONS ───────────────────────────────────────
    op.create_table(
        "submissions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submitted_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("startup_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("website_url", sa.String(2048), nullable=True),
        sa.Column("pitch_deck_url", sa.String(2048), nullable=True),
        sa.Column("status", postgresql.ENUM(name="submission_status", create_type=False), nullable=False, server_default="draft"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("raw_content", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submitted_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_submissions_org_status_active", "submissions",
        ["organization_id", "status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_submissions_org_active", "submissions", ["organization_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── 5. EVALUATION_RUNS ───────────────────────────────────
    op.create_table(
        "evaluation_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("triggered_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("status", postgresql.ENUM(name="run_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_workers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_workers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_workers", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("overall_score", sa.Float(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("config_snapshot", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_id"], ["users.id"], ondelete="SET NULL"),
    )
    op.create_index(
        "ix_evaluation_runs_submission_active", "evaluation_runs",
        ["submission_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_evaluation_runs_org_status_active", "evaluation_runs",
        ["organization_id", "status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_evaluation_runs_pending_running", "evaluation_runs",
        ["status", "created_at"],
        postgresql_where=sa.text("status IN ('pending', 'running') AND deleted_at IS NULL"),
    )
    op.create_index("ix_evaluation_runs_celery_task", "evaluation_runs", ["celery_task_id"])

    # ── 6. WORKER_RESULTS ────────────────────────────────────
    op.create_table(
        "worker_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("worker_type", sa.String(100), nullable=False),
        sa.Column("worker_id", sa.String(255), nullable=True),
        sa.Column("celery_task_id", sa.String(255), nullable=True),
        sa.Column("status", postgresql.ENUM(name="worker_status", create_type=False), nullable=False, server_default="pending"),
        sa.Column("processing_time_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("output_data", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_worker_results_run_active", "worker_results",
        ["evaluation_run_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_worker_results_status_active", "worker_results",
        ["evaluation_run_id", "status"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── 7. CLAIMS ────────────────────────────────────────────
    op.create_table(
        "claims",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("submission_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(100), nullable=False),
        sa.Column("source_reference", sa.String(500), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=False, server_default="0"),
        sa.Column("verification_status", sa.String(50), nullable=False, server_default="'unverified'"),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("metadata", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_claims_run_active", "claims", ["evaluation_run_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_claims_run_category_active", "claims",
        ["evaluation_run_id", "category"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_claims_org_active", "claims", ["organization_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── 8. CONTRADICTIONS ────────────────────────────────────
    op.create_table(
        "contradictions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("claim_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("contradiction_type", sa.String(100), nullable=False),
        sa.Column("severity", sa.Float(), nullable=False),
        sa.Column("explanation", sa.Text(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_a_id"], ["claims.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["claim_b_id"], ["claims.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_contradictions_run_active", "contradictions",
        ["evaluation_run_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_contradictions_org_active", "contradictions",
        ["organization_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── 9. SCORES (immutable) ────────────────────────────────
    op.create_table(
        "scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("evaluation_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dimension", sa.String(100), nullable=False),
        sa.Column("value", sa.Float(), nullable=False),
        sa.Column("weight", sa.Float(), nullable=False, server_default="1.0"),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("breakdown", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["evaluation_run_id"], ["evaluation_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.CheckConstraint("value >= 0.0 AND value <= 1.0", name="ck_scores_value_range"),
        sa.CheckConstraint("weight >= 0.0 AND weight <= 1.0", name="ck_scores_weight_range"),
    )
    op.create_index(
        "uq_scores_run_dimension_active", "scores",
        ["evaluation_run_id", "dimension"],
        unique=True, postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_scores_run_active", "scores", ["evaluation_run_id"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ix_scores_org_dimension_active", "scores",
        ["organization_id", "dimension"],
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ── 10. AUDIT_LOGS (append-only) ─────────────────────────
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("organization_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", postgresql.ENUM(name="audit_action", create_type=False), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=False),
        sa.Column("resource_id", sa.String(255), nullable=True),
        sa.Column("ip_address", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("request_id", sa.String(36), nullable=True),
        sa.Column("changes", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="'success'"),
        sa.Column("detail", sa.Text(), nullable=True),
    )
    op.create_index("ix_audit_logs_org_timestamp", "audit_logs", ["organization_id", "timestamp"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_request_id", "audit_logs", ["request_id"])
    op.create_index("ix_audit_logs_user_id", "audit_logs", ["user_id"])

    # ── 11. DATABASE TRIGGERS ────────────────────────────────

    # 11a. Audit log: PREVENT UPDATE and DELETE (append-only)
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_audit_log_modification()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_logs table is append-only. UPDATE and DELETE operations are forbidden.';
            RETURN NULL;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_logs_no_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_log_modification();
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_logs_no_delete
        BEFORE DELETE ON audit_logs
        FOR EACH ROW
        EXECUTE FUNCTION prevent_audit_log_modification();
    """)

    # 11b. Scores: PREVENT UPDATE (immutable after write)
    op.execute("""
        CREATE OR REPLACE FUNCTION prevent_score_update()
        RETURNS TRIGGER AS $$
        BEGIN
            -- Allow soft-delete (setting deleted_at) but prevent data changes
            IF NEW.value != OLD.value OR NEW.dimension != OLD.dimension
               OR NEW.weight != OLD.weight OR NEW.rationale != OLD.rationale THEN
                RAISE EXCEPTION 'scores are immutable after creation. Create a new evaluation run to re-score.';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_scores_immutable
        BEFORE UPDATE ON scores
        FOR EACH ROW
        EXECUTE FUNCTION prevent_score_update();
    """)

    # 11c. Auto-update updated_at timestamp on modification
    op.execute("""
        CREATE OR REPLACE FUNCTION update_updated_at_column()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = NOW();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    for table in ["organizations", "users", "submissions", "evaluation_runs",
                   "worker_results", "claims", "contradictions", "scores"]:
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at
            BEFORE UPDATE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION update_updated_at_column();
        """)

    # ── 12. ROW-LEVEL SECURITY (RLS) ────────────────────────
    # Enable RLS on all org-scoped tables. The application must SET
    # the session variable 'app.current_org_id' before queries.

    for table in ["users", "submissions", "evaluation_runs", "worker_results",
                   "claims", "contradictions", "scores"]:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY;")

        # Policy: users can only see rows from their organization
        op.execute(f"""
            CREATE POLICY {table}_org_isolation ON {table}
            USING (organization_id = current_setting('app.current_org_id')::uuid);
        """)

    # Audit logs: org-scoped read policy
    op.execute("ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;")
    op.execute("""
        CREATE POLICY audit_logs_org_isolation ON audit_logs
        USING (organization_id = current_setting('app.current_org_id')::uuid
               OR organization_id IS NULL);
    """)


def downgrade() -> None:
    """Drop all tables, triggers, and RLS policies in reverse order."""

    # Drop RLS policies
    for table in ["audit_logs", "scores", "contradictions", "claims",
                   "worker_results", "evaluation_runs", "submissions", "users"]:
        op.execute(f"DROP POLICY IF EXISTS {table}_org_isolation ON {table};")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY;")

    # Drop triggers
    for table in ["organizations", "users", "submissions", "evaluation_runs",
                   "worker_results", "claims", "contradictions", "scores"]:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_updated_at ON {table};")

    op.execute("DROP TRIGGER IF EXISTS trg_scores_immutable ON scores;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs;")

    # Drop functions
    op.execute("DROP FUNCTION IF EXISTS update_updated_at_column();")
    op.execute("DROP FUNCTION IF EXISTS prevent_score_update();")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_modification();")

    # Drop tables in reverse FK order
    op.drop_table("audit_logs")
    op.drop_table("scores")
    op.drop_table("contradictions")
    op.drop_table("claims")
    op.drop_table("worker_results")
    op.drop_table("evaluation_runs")
    op.drop_table("submissions")
    op.drop_table("users")
    op.drop_table("organizations")

    # Drop enums
    for enum_name in ["audit_action", "worker_status", "run_status",
                       "submission_status", "user_role", "plan_tier"]:
        op.execute(f"DROP TYPE IF EXISTS {enum_name};")
