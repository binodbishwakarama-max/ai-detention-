import React, { useState, useEffect } from 'react';
import { RefreshCw, CheckCircle, Cpu } from 'lucide-react';
import { ElevatedCard } from '../../components/ui/ElevatedCard';
import { useWebSocket } from '../../hooks/useWebSocket';
import type { WorkerProgress } from '../../types';

interface Props {
  activeRunId: string | null;
}

const WORKER_LABELS: Record<string, string> = {
  connected: 'Stream Connected',
  github_analysis: 'GitHub Analysis',
  pitch_deck: 'Pitch Deck Parser',
  video_analysis: 'Video Analysis',
  web_verification: 'Web Verification',
  cross_check: 'Cross-Check Engine',
  fabrication: 'Fabrication Detector',
  llm_judge: 'LLM Judge',
  finalize: 'Final Aggregator',
  final_aggregator: 'Final Aggregator',
};

export const EvaluationStream: React.FC<Props> = ({ activeRunId }) => {
  const [workers, setWorkers] = useState<Record<string, WorkerProgress>>({});

  const wsUrl = activeRunId
    ? `${(import.meta.env.VITE_WS_URL || 'ws://localhost:8000/api/v1')}/runs/${activeRunId}/stream`
    : '';

  const { data, isConnected, isConnecting, error } = useWebSocket<WorkerProgress>({
    url: wsUrl,
    enabled: !!activeRunId,
    reconnectAttempts: 8,
    reconnectInterval: 1500,
  });

  // Accumulate worker progress per worker_type
  useEffect(() => {
    if (data) {
      // eslint-disable-next-line
      setWorkers((prev) => ({
        ...prev,
        [data.worker_type]: data,
      }));
    }
  }, [data]);

  // Reset when run changes
  useEffect(() => {
    // eslint-disable-next-line
    setWorkers({});
  }, [activeRunId]);

  const workerEntries = Object.values(workers).sort((a, b) => {
    // Show active workers first
    if (a.progress >= 100 && b.progress < 100) return 1;
    if (a.progress < 100 && b.progress >= 100) return -1;
    return 0;
  });

  const overallProgress =
    workerEntries.length > 0
      ? Math.round(workerEntries.reduce((sum, w) => sum + w.progress, 0) / workerEntries.length)
      : 0;

  const allDone = workerEntries.length > 0 && workerEntries.every((w) => w.progress >= 100);

  return (
    <div>
      <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
        <RefreshCw
          size={18}
          color={isConnecting ? 'var(--amber-400)' : isConnected ? 'var(--emerald-500)' : 'var(--text-muted)'}
          style={isConnecting ? { animation: 'spin 1s linear infinite' } : undefined}
        />
        Live Pipeline
      </h3>

      {!activeRunId ? (
        <ElevatedCard style={{ textAlign: 'center', color: 'var(--text-muted)', padding: '3rem 1.5rem' }}>
          <Cpu size={28} style={{ opacity: 0.3, marginBottom: '0.75rem' }} />
          <p>Waiting for active evaluation…</p>
        </ElevatedCard>
      ) : (
        <ElevatedCard>
          {/* Connection status */}
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
            <span style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Run: <span style={{ fontFamily: 'monospace' }}>{activeRunId.substring(0, 8)}…</span>
            </span>
            <span style={{
              fontSize: '0.7rem',
              fontWeight: 600,
              textTransform: 'uppercase',
              letterSpacing: '0.05em',
              color: isConnected ? 'var(--emerald-400)' : 'var(--amber-400)',
            }}>
              {isConnected ? '● CONNECTED' : isConnecting ? '○ CONNECTING' : '○ DISCONNECTED'}
            </span>
          </div>

          {error && <div className="error-banner">{error}</div>}

          {/* Overall progress bar */}
          <div style={{ marginBottom: '1.25rem' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', textTransform: 'uppercase', fontWeight: 600 }}>Overall Pipeline</span>
              <span style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--emerald-400)' }}>{overallProgress}%</span>
            </div>
            <div className="progress-track">
              <div className="progress-fill" style={{ width: `${overallProgress}%` }} />
            </div>
          </div>

          {/* Per-worker progress */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {workerEntries.map((w) => (
              <div key={w.worker_type} style={{ padding: '0.6rem 0.75rem', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-sm)', border: '1px solid var(--border-subtle)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                  <span style={{ fontSize: '0.8rem', fontWeight: 600, color: w.progress >= 100 ? 'var(--emerald-400)' : 'var(--text-primary)' }}>
                    {w.progress >= 100 && <CheckCircle size={12} style={{ marginRight: '0.35rem', verticalAlign: 'text-bottom' }} />}
                    {WORKER_LABELS[w.worker_type] || w.worker_type}
                  </span>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>{w.progress}%</span>
                </div>
                <div className="progress-track" style={{ height: '4px' }}>
                  <div
                    className="progress-fill"
                    style={{
                      width: `${Math.min(100, w.progress)}%`,
                      background: w.progress >= 100
                        ? 'var(--emerald-500)'
                        : 'linear-gradient(90deg, var(--blue-400), var(--emerald-400))',
                    }}
                  />
                </div>
                <p style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginTop: '0.3rem' }}>{w.detail}</p>
              </div>
            ))}

            {workerEntries.length === 0 && (
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', textAlign: 'center', padding: '1rem 0' }}>
                Awaiting worker updates…
              </p>
            )}
          </div>

          {/* Completion banner */}
          {allDone && (
            <div style={{
              marginTop: '1.25rem',
              padding: '0.75rem 1rem',
              background: 'var(--emerald-glow)',
              borderRadius: 'var(--radius-sm)',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              color: 'var(--emerald-400)',
              fontSize: '0.85rem',
              fontWeight: 600,
            }}>
              <CheckCircle size={16} />
              Pipeline completed successfully.
            </div>
          )}
        </ElevatedCard>
      )}
    </div>
  );
};
