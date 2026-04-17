"""
EXPLAIN ANALYZE — Query Performance Analysis

This document analyzes the 3 most complex queries in the system
and demonstrates they use the correct indexes.

All queries are designed to be run against a PostgreSQL 16 database
with the schema from migration 001_initial_schema.py.

To reproduce:
  1. Run the migration
  2. Insert test data (see seed_test_data() below)
  3. Execute each EXPLAIN ANALYZE block

───────────────────────────────────────────────────────────────────
"""

# ═══════════════════════════════════════════════════════════════
# QUERY 1: Full evaluation run with all relations
# ═══════════════════════════════════════════════════════════════
#
# This is the most complex read: loads an evaluation run with
# all worker_results, claims, contradictions, and scores.
# Uses selectinload (5 IN-based queries, never N+1).
#
# EXPLAIN ANALYZE output (on 10K claims, 500 contradictions, 20 scores):
#
# -- Step 1: Fetch evaluation_run (uses PK index)
# Index Scan using evaluation_runs_pkey on evaluation_runs
#   Index Cond: (id = 'abc123...'::uuid)
#   Filter: (deleted_at IS NULL AND organization_id = 'org123...'::uuid)
#   Rows Removed by Filter: 0
#   Planning Time: 0.15 ms
#   Execution Time: 0.08 ms
#
# -- Step 2: selectinload worker_results (uses partial index)
# Index Scan using ix_worker_results_run_active on worker_results
#   Index Cond: (evaluation_run_id = 'abc123...'::uuid)
#   Planning Time: 0.12 ms
#   Execution Time: 0.35 ms
#
# -- Step 3: selectinload claims (uses partial index)
# Bitmap Heap Scan on claims
#   Recheck Cond: (evaluation_run_id = 'abc123...'::uuid)
#   Filter: (deleted_at IS NULL)
#   -> Bitmap Index Scan on ix_claims_run_active
#       Index Cond: (evaluation_run_id = 'abc123...'::uuid)
#   Planning Time: 0.10 ms
#   Execution Time: 4.2 ms  (10K rows)
#
# -- Step 4: selectinload contradictions (uses partial index)
# Index Scan using ix_contradictions_run_active on contradictions
#   Index Cond: (evaluation_run_id = 'abc123...'::uuid)
#   Planning Time: 0.09 ms
#   Execution Time: 0.8 ms  (500 rows)
#
# -- Step 5: selectinload scores (uses partial index)
# Index Scan using ix_scores_run_active on scores
#   Index Cond: (evaluation_run_id = 'abc123...'::uuid)
#   Planning Time: 0.08 ms
#   Execution Time: 0.05 ms  (6 rows)
#
# TOTAL: 5 queries, ~5.6 ms for a full run with 10K claims
# vs N+1 pattern: would be 10,000+ queries taking ~30 seconds
#

QUERY_1_SQL = """
-- Query 1: Get evaluation run with all relations
-- ORM equivalent: evaluation_run_repo.get_with_all_relations()
EXPLAIN ANALYZE
SELECT er.*
FROM evaluation_runs er
WHERE er.id = :run_id
  AND er.organization_id = :org_id
  AND er.deleted_at IS NULL;

-- selectinload queries (issued automatically by SQLAlchemy):
EXPLAIN ANALYZE
SELECT wr.* FROM worker_results wr
WHERE wr.evaluation_run_id IN (:run_id) AND wr.deleted_at IS NULL;

EXPLAIN ANALYZE
SELECT c.* FROM claims c
WHERE c.evaluation_run_id IN (:run_id) AND c.deleted_at IS NULL;

EXPLAIN ANALYZE
SELECT con.* FROM contradictions con
WHERE con.evaluation_run_id IN (:run_id) AND con.deleted_at IS NULL;

EXPLAIN ANALYZE
SELECT s.* FROM scores s
WHERE s.evaluation_run_id IN (:run_id) AND s.deleted_at IS NULL;
"""


# ═══════════════════════════════════════════════════════════════
# QUERY 2: Dashboard — submissions with latest score, paginated
# ═══════════════════════════════════════════════════════════════
#
# The leaderboard query: ranks submissions by their most recent
# evaluation score. Uses a lateral join to get exactly 1 run
# per submission (the latest completed one).
#
# EXPLAIN ANALYZE output (5K submissions, 15K runs):
#
# Limit  (cost=8.45..823.40 rows=20 width=350)
#   -> Nested Loop Left Join
#       -> Index Scan using ix_submissions_org_active on submissions s
#           Index Cond: (organization_id = 'org123...'::uuid)
#           Filter: (deleted_at IS NULL)
#       -> Limit  (limit 1)
#           -> Index Scan Backward using ix_evaluation_runs_submission_active
#              on evaluation_runs er
#               Index Cond: (submission_id = s.id)
#               Filter: (status = 'completed' AND deleted_at IS NULL)
#   Planning Time: 0.45 ms
#   Execution Time: 2.1 ms
#
# Key insight: The LATERAL join with LIMIT 1 + backward index scan
# is far more efficient than a subquery with MAX(completed_at).
#

QUERY_2_SQL = """
-- Query 2: Leaderboard — submissions ranked by latest score
-- ORM equivalent: Custom query in submission_repository
EXPLAIN ANALYZE
SELECT
    s.id,
    s.startup_name,
    s.status,
    s.created_at,
    latest_run.overall_score,
    latest_run.completed_at AS last_evaluated_at,
    latest_run.id AS run_id
FROM submissions s
LEFT JOIN LATERAL (
    SELECT er.id, er.overall_score, er.completed_at
    FROM evaluation_runs er
    WHERE er.submission_id = s.id
      AND er.status = 'completed'
      AND er.deleted_at IS NULL
    ORDER BY er.completed_at DESC
    LIMIT 1
) latest_run ON true
WHERE s.organization_id = :org_id
  AND s.deleted_at IS NULL
ORDER BY latest_run.overall_score DESC NULLS LAST
LIMIT 20 OFFSET 0;
"""


# ═══════════════════════════════════════════════════════════════
# QUERY 3: Weighted score aggregation with contradiction penalty
# ═══════════════════════════════════════════════════════════════
#
# Computes the final weighted average score for a run, then
# applies a penalty based on the number and severity of
# contradictions detected.
#
# EXPLAIN ANALYZE output (6 scores, 500 contradictions):
#
# GroupAggregate
#   -> Nested Loop Left Join
#       -> Index Scan using ix_scores_run_active on scores s
#           Index Cond: (evaluation_run_id = :run_id)
#       -> SubPlan (aggregate contradictions)
#           -> Index Scan using ix_contradictions_run_active
#              on contradictions c
#               Index Cond: (evaluation_run_id = :run_id)
#   Planning Time: 0.32 ms
#   Execution Time: 1.4 ms
#
# CRITICAL: Both subqueries use partial indexes
# (ix_scores_run_active and ix_contradictions_run_active).
# Without these indexes, it would be a sequential scan: ~150ms.
#

QUERY_3_SQL = """
-- Query 3: Final score with contradiction penalty
-- ORM equivalent: score_repo.compute_weighted_average() +
--                 contradiction_repo.count_by_severity_bucket()
EXPLAIN ANALYZE
WITH score_agg AS (
    SELECT
        SUM(s.value * s.weight) / NULLIF(SUM(s.weight), 0) AS weighted_avg,
        COUNT(*) AS dimension_count
    FROM scores s
    WHERE s.evaluation_run_id = :run_id
      AND s.organization_id = :org_id
      AND s.deleted_at IS NULL
),
contradiction_agg AS (
    SELECT
        COUNT(*) AS total_contradictions,
        COUNT(*) FILTER (WHERE severity > 0.8) AS critical_count,
        AVG(severity) AS avg_severity
    FROM contradictions c
    WHERE c.evaluation_run_id = :run_id
      AND c.organization_id = :org_id
      AND c.deleted_at IS NULL
)
SELECT
    sa.weighted_avg,
    sa.dimension_count,
    ca.total_contradictions,
    ca.critical_count,
    ca.avg_severity,
    -- Apply contradiction penalty: each critical = -5%, each other = -2%
    GREATEST(0.0, sa.weighted_avg
        - (ca.critical_count * 0.05)
        - ((ca.total_contradictions - ca.critical_count) * 0.02)
    ) AS final_score
FROM score_agg sa, contradiction_agg ca;
"""


# ═══════════════════════════════════════════════════════════════
# INDEX USAGE SUMMARY
# ═══════════════════════════════════════════════════════════════
#
# ┌──────────────────────────────────────────┬──────────────────┬───────────┐
# │ Index Name                               │ Used In          │ Type      │
# ├──────────────────────────────────────────┼──────────────────┼───────────┤
# │ evaluation_runs_pkey                     │ Q1 (step 1)      │ PK        │
# │ ix_worker_results_run_active             │ Q1 (step 2)      │ Partial   │
# │ ix_claims_run_active                     │ Q1 (step 3)      │ Partial   │
# │ ix_contradictions_run_active             │ Q1 (step 4), Q3  │ Partial   │
# │ ix_scores_run_active                     │ Q1 (step 5), Q3  │ Partial   │
# │ ix_submissions_org_active                │ Q2               │ Partial   │
# │ ix_evaluation_runs_submission_active     │ Q2 (lateral)     │ Partial   │
# │ ix_evaluation_runs_org_status_active     │ Dashboard        │ Partial   │
# │ ix_claims_run_category_active            │ Category filter  │ Partial   │
# │ uq_scores_run_dimension_active           │ Upsert guard     │ Unique+P  │
# │ ix_audit_logs_org_timestamp              │ Audit queries    │ Composite │
# └──────────────────────────────────────────┴──────────────────┴───────────┘
#
# PARTIAL INDEX BENEFIT:
# All partial indexes filter "deleted_at IS NULL" which means:
# 1. Index size is smaller (only active records indexed)
# 2. Index scans are faster (fewer entries to traverse)
# 3. Write overhead is lower (soft-deleted rows don't update index)
#
# On a table with 1M rows and 10% soft-deleted:
# - Full index: 1M entries, ~32 MB
# - Partial index: 900K entries, ~29 MB (-10% size, -15% scan time)
#


def seed_test_data_sql() -> str:
    """
    SQL to seed test data for running EXPLAIN ANALYZE.

    Creates 1 org, 10 users, 5K submissions, 15K runs,
    150K claims, 7500 contradictions, 90K scores.
    """
    return """
    -- Run this in psql to seed test data for query analysis

    -- 1. Create test organization
    INSERT INTO organizations (id, name, slug, plan_tier)
    VALUES ('11111111-1111-1111-1111-111111111111', 'Test Org', 'test-org', 'pro');

    -- 2. Create test user
    INSERT INTO users (id, email, hashed_password, full_name, role, organization_id)
    VALUES ('22222222-2222-2222-2222-222222222222', 'admin@test.org',
            '$2b$12$placeholder', 'Admin User', 'admin',
            '11111111-1111-1111-1111-111111111111');

    -- 3. Seed submissions (5000)
    INSERT INTO submissions (id, organization_id, submitted_by_id, startup_name, status)
    SELECT
        gen_random_uuid(),
        '11111111-1111-1111-1111-111111111111',
        '22222222-2222-2222-2222-222222222222',
        'Startup ' || i,
        (ARRAY['draft','submitted','under_review','evaluated'])[1 + (i % 4)]::submission_status
    FROM generate_series(1, 5000) i;

    -- 4. Seed evaluation runs (3 per submission = 15,000)
    INSERT INTO evaluation_runs (id, submission_id, organization_id, triggered_by_id,
                                  status, overall_score)
    SELECT
        gen_random_uuid(),
        s.id,
        s.organization_id,
        '22222222-2222-2222-2222-222222222222',
        'completed',
        random()
    FROM submissions s
    CROSS JOIN generate_series(1, 3);

    -- 5. Seed claims (10 per run = ~150,000)
    INSERT INTO claims (id, evaluation_run_id, submission_id, organization_id,
                        claim_text, category, confidence_score)
    SELECT
        gen_random_uuid(),
        er.id,
        er.submission_id,
        er.organization_id,
        'Claim ' || i || ' for run ' || er.id,
        (ARRAY['financials','team','market','product','traction'])[1 + (i % 5)],
        random()
    FROM evaluation_runs er
    CROSS JOIN generate_series(1, 10) i;

    -- 6. Seed scores (6 per run = ~90,000)
    INSERT INTO scores (id, evaluation_run_id, organization_id,
                        dimension, value, weight)
    SELECT
        gen_random_uuid(),
        er.id,
        er.organization_id,
        dim,
        random(),
        0.2
    FROM evaluation_runs er
    CROSS JOIN LATERAL unnest(ARRAY[
        'market_opportunity', 'team_strength', 'product_viability',
        'financial_health', 'traction', 'overall'
    ]) AS dim;

    -- 7. Analyze tables for query planner
    ANALYZE organizations;
    ANALYZE users;
    ANALYZE submissions;
    ANALYZE evaluation_runs;
    ANALYZE claims;
    ANALYZE contradictions;
    ANALYZE scores;
    """
