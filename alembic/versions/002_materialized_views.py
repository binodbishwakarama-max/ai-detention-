"""materialized views

Revision ID: 002_materialized_views
Revises: 001_initial_schema
Create Date: 2026-04-16 02:40:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '002_materialized_views'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Create L3 Materialized View for Organization Stats ────────────
    # Computes expensive aggregations once, eliminating heavy JOIN GROUP BY queries.
    op.execute("""
    CREATE MATERIALIZED VIEW org_dashboard_stats AS
    SELECT 
        o.id as organization_id,
        o.name as organization_name,
        COUNT(DISTINCT s.id) as total_submissions_count,
        COUNT(DISTINCT er.id) as total_evaluations_count,
        COALESCE(AVG(er.overall_score), 0) as average_overall_score,
        MAX(er.updated_at) as last_evaluation_date
    FROM organizations o
    LEFT JOIN submissions s ON s.organization_id = o.id AND s.deleted_at IS NULL
    LEFT JOIN evaluation_runs er ON er.organization_id = o.id AND er.deleted_at IS NULL
    WHERE o.deleted_at IS NULL
    GROUP BY o.id;
    """)

    # Setup unique index allowing REFRESH MATERIALIZED VIEW CONCURRENTLY (reads aren't blocked)
    op.execute("""
    CREATE UNIQUE INDEX uq_org_dashboard_stats 
    ON org_dashboard_stats(organization_id);
    """)

    # Function to trigger concurrently. 
    # Usually fired by a Celery Cron or Event hook, not DB Triggers.
    op.execute("""
    CREATE OR REPLACE FUNCTION refresh_org_dashboard_stats()
    RETURNS void AS $$
    BEGIN
        REFRESH MATERIALIZED VIEW CONCURRENTLY org_dashboard_stats;
    END;
    $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS refresh_org_dashboard_stats;")
    op.execute("DROP MATERIALIZED VIEW IF EXISTS org_dashboard_stats;")
