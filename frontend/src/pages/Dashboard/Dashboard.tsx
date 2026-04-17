import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Play, Clock, ArrowRight } from 'lucide-react';
import { runsApi, configsApi } from '../../api/endpoints';
import { StatsCards } from './StatsCards';
import { ElevatedCard } from '../../components/ui/ElevatedCard';
import { Button } from '../../components/ui/Button';
import type { EvaluationRun } from '../../types';

const statusBadge = (status: string) => {
  const cls = `badge badge-${status}`;
  return <span className={cls}>{status}</span>;
};

const timeAgo = (dateStr: string | null) => {
  if (!dateStr) return '—';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
};

export const Dashboard: React.FC = () => {
  const navigate = useNavigate();

  // Fetch recent runs (auto-refresh every 10s)
  const { data: runsData, isLoading: runsLoading } = useQuery({
    queryKey: ['runs', 'recent'],
    queryFn: () => runsApi.list({ page: 1, page_size: 10 }),
    select: (res) => res.data,
    refetchInterval: 10_000,
  });

  // Fetch configs count
  const { data: configsData, isLoading: configsLoading } = useQuery({
    queryKey: ['configs', 'list'],
    queryFn: () => configsApi.list(1, 100),
    select: (res) => res.data,
  });

  const runs = runsData?.items ?? [];
  const totalEvals = runsData?.total ?? 0;

  const completedRuns = runs.filter((r) => r.status === 'completed');
  const activeRuns = runs.filter((r) => r.status === 'running' || r.status === 'pending');

  const avgScore =
    completedRuns.length > 0
      ? completedRuns.reduce((sum, r) => sum + (r.overall_score ?? 0), 0) / completedRuns.length
      : 0;

  const successRate =
    totalEvals > 0
      ? (completedRuns.length / Math.max(runs.length, 1)) * 100
      : 0;

  const triggerRun = async (configId: string) => {
    try {
      const { data: run } = await runsApi.create({
        config_id: configId,
        metadata: { source: 'dashboard' },
      });
      navigate(`/evaluations/${run.id}`);
    } catch {
      // toast will handle via interceptor
    }
  };

  return (
    <div className="animate-in">
      <div className="page-header">
        <div>
          <h2 className="page-title">Dashboard</h2>
          <p className="page-subtitle">Real-time evaluation pipeline overview</p>
        </div>
      </div>

      {/* KPI Stats */}
      <StatsCards
        totalEvaluations={totalEvals}
        avgScore={avgScore}
        activeRuns={activeRuns.length}
        successRate={successRate}
        isLoading={runsLoading}
      />

      <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr', gap: '1.5rem' }}>
        {/* Recent Runs Table */}
        <ElevatedCard>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.25rem' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 600 }}>Recent Runs</h3>
            <Button variant="secondary" onClick={() => navigate('/evaluations')} style={{ fontSize: '0.75rem', padding: '0.4rem 0.75rem' }}>
              View All <ArrowRight size={14} />
            </Button>
          </div>

          {runsLoading ? (
            <p style={{ color: 'var(--text-muted)', padding: '2rem 0', textAlign: 'center' }}>Loading…</p>
          ) : runs.length === 0 ? (
            <div className="empty-state">
              <Clock size={32} className="empty-state-icon" />
              <p>No evaluation runs yet. Trigger one from a configuration.</p>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>Run ID</th>
                  <th>Status</th>
                  <th>Score</th>
                  <th>Created</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {runs.slice(0, 8).map((run: EvaluationRun) => (
                  <tr key={run.id} style={{ cursor: 'pointer' }} onClick={() => navigate(`/evaluations/${run.id}`)}>
                    <td style={{ fontFamily: 'monospace', fontSize: '0.8rem' }}>
                      {run.id.substring(0, 8)}…
                    </td>
                    <td>{statusBadge(run.status)}</td>
                    <td style={{ fontWeight: 600, color: run.overall_score ? 'var(--emerald-400)' : 'var(--text-muted)' }}>
                      {run.overall_score ? `${(run.overall_score * 100).toFixed(1)}%` : '—'}
                    </td>
                    <td style={{ fontSize: '0.8rem' }}>{timeAgo(run.created_at)}</td>
                    <td>
                      <ArrowRight size={14} color="var(--text-muted)" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </ElevatedCard>

        {/* Quick Actions — configs */}
        <ElevatedCard>
          <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1.25rem' }}>Quick Execute</h3>

          {configsLoading ? (
            <p style={{ color: 'var(--text-muted)' }}>Loading configs…</p>
          ) : !configsData?.items?.length ? (
            <div className="empty-state" style={{ padding: '2rem 0' }}>
              <p style={{ fontSize: '0.85rem' }}>No configs found.</p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {configsData.items.slice(0, 5).map((cfg) => (
                <div
                  key={cfg.id}
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    padding: '0.75rem',
                    background: 'var(--bg-tertiary)',
                    borderRadius: 'var(--radius-sm)',
                    border: '1px solid var(--border-subtle)',
                  }}
                >
                  <div>
                    <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>{cfg.name}</div>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>v{cfg.version}</div>
                  </div>
                  <button className="btn btn-primary" style={{ padding: '0.4rem 0.75rem', fontSize: '0.75rem' }} onClick={() => triggerRun(cfg.id)}>
                    <Play size={12} /> Run
                  </button>
                </div>
              ))}
            </div>
          )}
        </ElevatedCard>
      </div>
    </div>
  );
};
