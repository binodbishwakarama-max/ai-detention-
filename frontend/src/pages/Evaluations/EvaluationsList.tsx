import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { ArrowRight, Filter } from 'lucide-react';
import { runsApi } from '../../api/endpoints';
import { ElevatedCard } from '../../components/ui/ElevatedCard';
import { Button } from '../../components/ui/Button';
import type { RunStatus } from '../../types';

const STATUS_OPTIONS: Array<{ label: string; value: RunStatus | '' }> = [
  { label: 'All', value: '' },
  { label: 'Running', value: 'running' },
  { label: 'Pending', value: 'pending' },
  { label: 'Completed', value: 'completed' },
  { label: 'Failed', value: 'failed' },
  { label: 'Cancelled', value: 'cancelled' },
];

const statusBadge = (status: string) => (
  <span className={`badge badge-${status}`}>{status}</span>
);

export const EvaluationsList: React.FC = () => {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const pageSize = 15;

  const { data, isLoading } = useQuery({
    queryKey: ['runs', 'list', page, statusFilter],
    queryFn: () =>
      runsApi.list({
        page,
        page_size: pageSize,
        ...(statusFilter ? { status: statusFilter } : {}),
      }),
    select: (res) => res.data,
    refetchInterval: 15_000,
  });

  const runs = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="animate-in">
      <div className="page-header" style={{ marginBottom: '2.5rem' }}>
        <div>
          <h2 className="page-title">Evaluations</h2>
          <p className="page-subtitle">
            Historical record of AI performance and pipeline executions
          </p>
        </div>
        <div style={{ fontSize: '0.85rem', color: 'var(--text-muted)', background: 'var(--bg-tertiary)', padding: '0.5rem 1rem', borderRadius: 'var(--radius-pill)', fontWeight: 500 }}>
          {data?.total ?? 0} total runs
        </div>
      </div>

      <div className="filter-chip-group" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Filter size={16} color="var(--text-muted)" />
          <div style={{ display: 'flex', gap: '0.5rem', overflowX: 'auto', padding: '4px' }}>
            {STATUS_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={statusFilter === opt.value ? 'chip chip-active' : 'chip'}
                onClick={() => { setStatusFilter(opt.value); setPage(1); }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <ElevatedCard>
        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '5rem 0', gap: '1rem' }}>
            <div className="spinner" />
            <p style={{ color: 'var(--text-muted)' }}>Loading evaluation runs…</p>
          </div>
        ) : runs.length === 0 ? (
          <div className="empty-state" style={{ padding: '6rem 0' }}>
            <p style={{ color: 'var(--text-secondary)', marginBottom: '1rem' }}>No evaluation runs match this filter.</p>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Run ID</th>
                <th>Status</th>
                <th>Overall Score</th>
                <th>Progress</th>
                <th>Execution Time</th>
                <th style={{ width: 48 }}></th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => (
                <tr
                  key={run.id}
                  onClick={() => navigate(`/evaluations/${run.id}`)}
                >
                  <td style={{ fontFamily: 'monospace', fontSize: '0.8rem', color: 'var(--google-blue)', fontWeight: 500 }}>
                    {run.id.substring(0, 8)}…
                  </td>
                  <td>{statusBadge(run.status)}</td>
                  <td>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                      <span style={{ fontWeight: 600, fontSize: '1rem', color: run.overall_score != null ? 'var(--google-green)' : 'var(--text-muted)' }}>
                        {run.overall_score != null ? `${(run.overall_score * 100).toFixed(1)}%` : '—'}
                      </span>
                      {run.overall_score != null && (
                        <div style={{ width: 48, height: 4, background: 'var(--bg-tertiary)', borderRadius: 2, overflow: 'hidden' }}>
                          <div style={{ width: `${run.overall_score * 100}%`, height: '100%', background: 'var(--google-green)' }} />
                        </div>
                      )}
                    </div>
                  </td>
                  <td>
                    <div style={{ fontSize: '0.85rem' }}>
                      <span style={{ fontWeight: 640 }}>{run.completed_workers}</span>
                      <span style={{ color: 'var(--text-muted)' }}> / {run.total_workers}</span>
                    </div>
                  </td>
                  <td style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
                     {run.completed_at && run.started_at ? (
                       <span>
                         {new Date(run.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })} • {Math.round((new Date(run.completed_at).getTime() - new Date(run.started_at).getTime()) / 1000)}s
                       </span>
                     ) : run.started_at ? (
                       <span>Started {new Date(run.started_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                     ) : (
                       <span>Pending</span>
                     )}
                  </td>
                  <td>
                    <div className="action-circle">
                      <ArrowRight size={14} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {totalPages > 1 && (
          <div className="pagination">
            <Button
              variant="secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem' }}
            >
              Previous
            </Button>
            <div className="pagination-info">
              Page {page} of {totalPages}
            </div>
            <Button
              variant="secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem' }}
            >
              Next
            </Button>
          </div>
        )}
      </ElevatedCard>
    </div>
  );
};
