import React from 'react';
import { Activity, Server } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

export const Header: React.FC = () => {
  const { user } = useAuth();

  return (
    <header style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '3rem', paddingBottom: '1rem', borderBottom: '1px solid var(--border-color)' }}>
      <div style={{ background: 'var(--emerald-500)', padding: '0.75rem', borderRadius: 'var(--radius-md)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Activity size={24} color="var(--bg-primary)" />
      </div>
      <div>
        <h1 style={{ fontSize: '1.5rem', fontWeight: 700, margin: 0, letterSpacing: '-0.025em' }}>AI Evaluation Engine</h1>
        <p style={{ color: 'var(--text-secondary)', margin: 0, fontSize: '0.875rem' }}>Production-grade model validation matrix</p>
      </div>
      
      <div style={{ marginLeft: 'auto', display: 'flex', gap: '0.5rem', alignItems: 'center' }}>
          <Server size={16} color="var(--emerald-500)" className="active-pulse" style={{ borderRadius: '50%' }} />
          <span style={{ fontSize: '0.875rem', color: 'var(--emerald-500)', fontWeight: 500 }}>System Online</span>
          {user && (
            <span style={{ marginLeft: '1rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
              {user.full_name}
            </span>
          )}
      </div>
    </header>
  );
};
