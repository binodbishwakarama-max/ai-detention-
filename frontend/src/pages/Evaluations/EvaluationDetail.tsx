import React from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { ArrowLeft, XCircle, Download, Activity, Target, Zap, Clock, Hash, BarChart3 } from 'lucide-react';
import { runsApi, resultsApi } from '../../api/endpoints';
import { EvaluationStream } from './EvaluationStream';
import { ElevatedCard } from '../../components/ui/ElevatedCard';
import { Button } from '../../components/ui/Button';

const statusBadge = (status: string) => (
  <span className={`badge badge-${status}`}>{status}</span>
);

export const EvaluationDetail: React.FC = () => {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();

  const { data: run, isLoading, refetch } = useQuery({
    queryKey: ['run', runId],
    queryFn: () => runsApi.get(runId!),
    select: (res) => res.data,
    enabled: !!runId,
    refetchInterval: (query) => {
      const runData = query.state.data;
      const status = runData?.status;
      return status === 'completed' || status === 'failed' || status === 'cancelled'
        ? false
        : 5_000;
    },
  });

  const { data: summary } = useQuery({
    queryKey: ['run', runId, 'summary'],
    queryFn: () => resultsApi.summary(runId!),
    select: (res) => res.data,
    enabled: !!runId && run?.status === 'completed',
  });

  const handleCancel = async () => {
    if (!runId) return;
    try {
      await runsApi.cancel(runId);
      refetch();
    } catch { /* toast handles */ }
  };

  const handleExport = async (format: 'json' | 'csv') => {
    if (!runId) return;
    try {
      const { data } = await resultsApi.export(runId, format);
      window.open(data.download_url, '_blank');
    } catch { /* toast handles */ }
  };

  if (isLoading) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '10rem 0' }}>
      <div className="spinner" />
    </div>
  );

  const isLive = run?.status === 'running' || run?.status === 'pending';

  return (
    <div className="animate-in">
      {/* Header */}
      <div className="page-header" style={{ marginBottom: '2.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
          <button 
            className="action-circle" 
            onClick={() => navigate('/evaluations')}
            style={{ border: '1px solid var(--border-color)', width: 40, height: 40 }}
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <h2 className="page-title">Run {runId?.substring(0, 8)}</h2>
              {run && statusBadge(run.status)}
            </div>
            <p className="page-subtitle">
              {run ? `Started ${run.started_at ? new Date(run.started_at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : 'Pending'}` : 'Loading…'}
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          {isLive && (
            <Button variant="secondary" onClick={handleCancel} style={{ color: 'var(--google-red)' }}>
              <XCircle size={16} /> Cancel Run
            </Button>
          )}
          {run?.status === 'completed' && (
            <>
              <Button variant="secondary" onClick={() => handleExport('json')}>
                <Download size={16} /> JSON
              </Button>
              <Button variant="secondary" onClick={() => handleExport('csv')}>
                <Download size={16} /> CSV
              </Button>
            </>
          )}
        </div>
      </div>

      {!run ? (
        <div className="error-banner">Run not found.</div>
      ) : (
        <div className="details-grid" style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '2rem' }}>
          {/* Left: Performance & Results */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            
            {/* KPI Cards for Summary Results */}
            {summary && (
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '1.25rem' }}>
                <ElevatedCard style={{ padding: '1.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Analysis Workers</span>
                    <Target size={16} color="var(--google-green)" />
                  </div>
                  <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--google-green)' }}>
                    {summary.completed_workers} / {summary.total_workers}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                    Analysis steps completed
                  </div>
                </ElevatedCard>

                <ElevatedCard style={{ padding: '1.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Claims Extracted</span>
                    <Zap size={16} color="var(--google-blue)" />
                  </div>
                  <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--text-primary)' }}>
                    {summary.total_claims}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                    Fact-checked points
                  </div>
                </ElevatedCard>

                <ElevatedCard style={{ padding: '1.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
                    <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', textTransform: 'uppercase' }}>Contradictions</span>
                    <Activity size={16} color="var(--google-red)" />
                  </div>
                  <div style={{ fontSize: '1.75rem', fontWeight: 700, color: 'var(--google-red)' }}>
                    {summary.total_contradictions}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', marginTop: '0.25rem' }}>
                    Conflicts detected
                  </div>
                </ElevatedCard>
              </div>
            )}

            {/* Run Metadata Detail */}
            <ElevatedCard>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Hash size={20} color="var(--google-blue)" /> Execution Context
              </h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
                {[
                  ['Config ID', run.config_id ? run.config_id.substring(0, 12) + '…' : 'None', <Zap size={14} />],
                  ['Run Status', run.status.toUpperCase(), <Activity size={14} />],
                  ['Analysis Workers', run.total_workers, <BarChart3 size={14} />],
                  ['Overall Score', run.overall_score != null ? `${(run.overall_score * 100).toFixed(1)}%` : 'Processing…', <Target size={14} />],
                  ['Start Time', run.started_at ? new Date(run.started_at).toLocaleTimeString() : 'Pending', <Clock size={14} />],
                  ['End Time', run.completed_at ? new Date(run.completed_at).toLocaleTimeString() : 'In Progress', <Clock size={14} />],
                ].map(([label, value, icon]) => (
                  <div key={label as string} style={{ borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.75rem' }}>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, marginBottom: '0.4rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      {icon} {label}
                    </div>
                    <div style={{ fontSize: '0.95rem', fontWeight: 500, color: 'var(--text-primary)' }}>{value}</div>
                  </div>
                ))}
              </div>
            </ElevatedCard>

            {/* Metric scores breakdown */}
            {summary && summary.scores.length > 0 && (
              <ElevatedCard>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                  <BarChart3 size={20} color="var(--google-green)" /> Dimension Analysis
                </h3>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
                  {summary.scores.map((score: any) => (
                    <div key={score.dimension}>
                      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                        <div>
                          <span style={{ fontSize: '0.9rem', fontWeight: 500, color: 'var(--text-secondary)', textTransform: 'capitalize' }}>
                            {score.dimension.replace(/_/g, ' ')}
                          </span>
                          {score.rationale && (
                            <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>{score.rationale}</p>
                          )}
                        </div>
                        <span style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--google-green)' }}>
                          {(score.value * 100).toFixed(1)}%
                        </span>
                      </div>
                      <div style={{ width: '100%', height: 8, background: 'var(--bg-tertiary)', borderRadius: 4, overflow: 'hidden' }}>
                        <div style={{ width: `${score.value * 100}%`, height: '100%', background: 'var(--google-green)', transition: 'width 0.8s ease' }} />
                      </div>
                    </div>
                  ))}
                </div>
              </ElevatedCard>
            )}
          </div>

          {/* Right: Live execution stream */}
          <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
            <EvaluationStream activeRunId={isLive ? runId! : null} />
          </div>
        </div>
      )}
    </div>
  );
};
