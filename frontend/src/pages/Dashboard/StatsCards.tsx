import React from 'react';
import { FlaskConical, TrendingUp, Zap, CheckCircle } from 'lucide-react';

interface StatsCardsProps {
  totalEvaluations: number;
  avgScore: number;
  activeRuns: number;
  successRate: number;
  isLoading?: boolean;
}

const cards = [
  {
    key: 'total',
    label: 'Total Evaluations',
    icon: FlaskConical,
    color: 'var(--emerald-500)',
    bg: 'var(--emerald-glow)',
    getValue: (p: StatsCardsProps) => p.totalEvaluations.toLocaleString(),
  },
  {
    key: 'score',
    label: 'Avg Score',
    icon: TrendingUp,
    color: 'var(--blue-400)',
    bg: 'var(--blue-glow)',
    getValue: (p: StatsCardsProps) =>
      p.avgScore > 0 ? `${(p.avgScore * 100).toFixed(1)}%` : '—',
  },
  {
    key: 'active',
    label: 'Active Runs',
    icon: Zap,
    color: 'var(--amber-400)',
    bg: 'var(--amber-glow)',
    getValue: (p: StatsCardsProps) => p.activeRuns.toString(),
  },
  {
    key: 'success',
    label: 'Success Rate',
    icon: CheckCircle,
    color: 'var(--emerald-400)',
    bg: 'var(--emerald-glow)',
    getValue: (p: StatsCardsProps) =>
      p.successRate > 0 ? `${p.successRate.toFixed(1)}%` : '—',
  },
];

export const StatsCards: React.FC<StatsCardsProps> = (props) => {
  return (
    <div className="stats-grid">
      {cards.map(({ key, label, icon: Icon, color, bg, getValue }) => (
        <div key={key} className="stat-card animate-in">
          <div className="stat-card-header">
            <span className="stat-card-label">{label}</span>
            <div
              className="stat-card-icon"
              style={{ background: bg }}
            >
              <Icon size={18} color={color} />
            </div>
          </div>
          <div className="stat-card-value" style={{ color }}>
            {props.isLoading ? '…' : getValue(props)}
          </div>
        </div>
      ))}
    </div>
  );
};
