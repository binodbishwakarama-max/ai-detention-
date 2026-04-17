import { apiClient } from './client';
import type {
  TokenResponse,
  LoginPayload,
  RegisterPayload,
  User,
  EvalConfig,
  EvaluationRun,
  EvalRunCreate,
  ResultSummary,
  Dataset,
  Metric,
  PaginatedResponse,
  Submission,
  SubmissionCreate,
  SubmissionUpdate,
} from '../types';

// ── Auth ────────────────────────────────────────────────

export const authApi = {
  login: (data: LoginPayload) =>
    apiClient.post<TokenResponse>('/auth/login', data),

  register: (data: RegisterPayload) =>
    apiClient.post<User>('/auth/register', data),

  refresh: (refresh_token: string) =>
    apiClient.post<TokenResponse>('/auth/refresh', { refresh_token }),

  me: () => apiClient.get<User>('/auth/me'),

  logout: () => apiClient.post('/auth/logout'),
};

// ── Submissions ──────────────────────────────────────────

export const submissionsApi = {
  list: (params?: { page?: number; page_size?: number; status?: string }) =>
    apiClient.get<PaginatedResponse<Submission>>('/submissions', { params }),

  get: (id: string) =>
    apiClient.get<Submission>(`/submissions/${id}`),

  create: (data: SubmissionCreate) =>
    apiClient.post<Submission>('/submissions', data),

  update: (id: string, data: SubmissionUpdate) =>
    apiClient.patch<Submission>(`/submissions/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/submissions/${id}`),

  evaluate: (id: string, config_id: string, metadata?: Record<string, unknown>) =>
    apiClient.post<EvaluationRun>(`/submissions/${id}/evaluate`, { config_id, metadata }),
};

// ── Evaluations: Configs ────────────────────────────────

export const configsApi = {
  list: (page = 1, page_size = 20) =>
    apiClient.get<PaginatedResponse<EvalConfig>>('/evaluations/configs', {
      params: { page, page_size },
    }),

  get: (id: string) =>
    apiClient.get<EvalConfig>(`/evaluations/configs/${id}`),

  create: (data: Partial<EvalConfig>) =>
    apiClient.post<EvalConfig>('/evaluations/configs', data),

  update: (id: string, data: Partial<EvalConfig>) =>
    apiClient.patch<EvalConfig>(`/evaluations/configs/${id}`, data),

  delete: (id: string) =>
    apiClient.delete(`/evaluations/configs/${id}`),
};

// ── Evaluations: Runs ───────────────────────────────────

export const runsApi = {
  list: (params?: { page?: number; page_size?: number; config_id?: string; status?: string }) =>
    apiClient.get<PaginatedResponse<EvaluationRun>>('/evaluations/runs', { params }),

  get: (id: string) =>
    apiClient.get<EvaluationRun>(`/evaluations/runs/${id}`),

  create: (data: EvalRunCreate) =>
    apiClient.post<EvaluationRun>('/evaluations/runs', data),

  cancel: (id: string) =>
    apiClient.post<EvaluationRun>(`/evaluations/runs/${id}/cancel`),
};

// ── Results ─────────────────────────────────────────────

export const resultsApi = {
  list: (runId: string, page = 1, page_size = 50) =>
    apiClient.get(`/results/run/${runId}/workers`, { params: { page, page_size } }),

  summary: (runId: string) =>
    apiClient.get<ResultSummary>(`/results/run/${runId}/summary`),

  export: (runId: string, format: 'json' | 'csv' = 'json') =>
    apiClient.post<{ download_url: string }>(`/results/run/${runId}/export`, null, {
      params: { format },
    }),
};

// ── Datasets ────────────────────────────────────────────

export const datasetsApi = {
  list: (page = 1, page_size = 20) =>
    apiClient.get<PaginatedResponse<Dataset>>('/datasets', {
      params: { page, page_size },
    }),

  get: (id: string) =>
    apiClient.get<Dataset>(`/datasets/${id}`),
};

// ── Metrics ─────────────────────────────────────────────

export const metricsApi = {
  list: (page = 1, page_size = 50) =>
    apiClient.get<PaginatedResponse<Metric>>('/metrics', {
      params: { page, page_size },
    }),

  get: (id: string) =>
    apiClient.get<Metric>(`/metrics/${id}`),
};

// ── Health ──────────────────────────────────────────────

export const healthApi = {
  check: () => apiClient.get('/health'),
};
