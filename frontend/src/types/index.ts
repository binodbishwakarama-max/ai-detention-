// ── Auth ────────────────────────────────────────────────

export type Role = 'admin' | 'member' | 'viewer';

export interface User {
  id: string;
  email: string;
  full_name: string;
  organization_id: string;
  role: Role;
  is_active: boolean;
  mfa_enabled: boolean;
  last_login_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
}

export interface LoginPayload {
  email: string;
  password: string;
}

export interface RegisterPayload {
  email: string;
  password: string;
  full_name: string;
  organization_name: string;
}

// ── Evaluations ─────────────────────────────────────────

export type RunStatus =
  | 'pending'
  | 'running'
  | 'completed'
  | 'failed'
  | 'cancelled';

export interface EvalConfig {
  id: string;
  name: string;
  description: string | null;
  dataset_id: string | null;
  model_config: Record<string, unknown>;
  metrics_config: unknown[];
  parameters: Record<string, unknown>;
  webhook_url: string | null;
  is_template: boolean;
  version: number;
  created_at: string;
  updated_at: string;
}

export interface EvaluationRun {
  id: string;
  submission_id: string;
  config_id: string | null;
  organization_id: string;
  triggered_by_id: string | null;
  status: RunStatus;
  started_at: string | null;
  completed_at: string | null;
  total_workers: number;
  completed_workers: number;
  failed_workers: number;
  overall_score: number | null;
  error_message: string | null;
  celery_task_id: string | null;
  config_snapshot: Record<string, unknown>;
  run_metadata: Record<string, unknown>;
  progress_pct: number;
  created_at: string;
  updated_at: string;
}

export interface EvalRunCreate {
  config_id: string;
  metadata?: Record<string, unknown>;
}

export interface DimensionScore {
  dimension: string;
  value: number;
  rationale?: string;
}

// ── Results ─────────────────────────────────────────────

export interface ResultSummary {
  run_id: string;
  status: string;
  overall_score: number | null;
  total_workers: number;
  completed_workers: number;
  failed_workers: number;
  total_claims: number;
  total_contradictions: number;
  scores: DimensionScore[];
  progress_pct: number;
}

// ── Dashboard / Stats ───────────────────────────────────

export interface OrgDashboardStats {
  organization_id: string;
  organization_name: string;
  total_submissions_count: number;
  total_evaluations_count: number;
  average_overall_score: number;
  last_evaluation_date: string | null;
}

// ── Workers / Streaming ─────────────────────────────────

export interface WorkerProgress {
  worker_type: string;
  progress: number;
  detail: string;
  updated_at: string;
}

// ── Datasets ────────────────────────────────────────────

export interface Dataset {
  id: string;
  name: string;
  description: string | null;
  status: 'pending' | 'processing' | 'ready' | 'error';
  sample_count: number;
  file_url: string | null;
  created_at: string;
  updated_at: string;
}

// ── Metrics ─────────────────────────────────────────────

export interface Metric {
  id: string;
  name: string;
  display_name: string;
  description: string | null;
  metric_type: string;
  higher_is_better: boolean;
  min_value: number;
  max_value: number;
  is_built_in: boolean;
  created_at: string;
}

// ── Pagination ──────────────────────────────────────────

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// ── Submissions ──────────────────────────────────────────

export type SubmissionStatus =
  | 'draft'
  | 'submitted'
  | 'under_review'
  | 'evaluated'
  | 'archived';

export interface Submission {
  id: string;
  organization_id: string;
  submitted_by_id: string | null;
  startup_name: string;
  description: string | null;
  website_url: string | null;
  pitch_deck_url: string | null;
  status: SubmissionStatus;
  metadata: Record<string, unknown>;
  raw_content: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface SubmissionCreate {
  startup_name: string;
  description?: string;
  website_url?: string;
  pitch_deck_url?: string;
  metadata?: Record<string, unknown>;
}

export interface SubmissionUpdate {
  startup_name?: string;
  description?: string;
  website_url?: string;
  pitch_deck_url?: string;
  status?: SubmissionStatus;
  metadata?: Record<string, unknown>;
}
