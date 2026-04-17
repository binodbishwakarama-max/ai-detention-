import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Rocket,
  FlaskConical,
  Database,
  BarChart3,
  Settings,
  Shield,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', end: true },
  { to: '/submissions', icon: Rocket, label: 'Submissions' },
  { to: '/evaluations', icon: FlaskConical, label: 'Evaluations' },
  { to: '/datasets', icon: Database, label: 'Datasets' },
  { to: '/metrics', icon: BarChart3, label: 'Metrics' },
  { to: '/settings', icon: Settings, label: 'Settings' },
];

export const Sidebar: React.FC = () => {
  const { user } = useAuth();

  return (
    <aside className="sidebar">
      {/* Brand */}
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">
          <Shield size={18} strokeWidth={2.5} color="currentColor" />
        </div>
        <div>
          <h1 className="sidebar-title">Eval Engine</h1>
        </div>
      </div>

      <div style={{ padding: '0 24px', marginBottom: '8px' }}>
         <span className="sidebar-subtitle">Platform Navigation</span>
      </div>

      {/* Navigation */}
      <nav className="sidebar-nav">
        {navItems.map(({ to, icon: Icon, label, end }) => (
          <NavLink
            key={to}
            to={to}
            end={end}
            className={({ isActive }) =>
              `sidebar-link ${isActive ? 'sidebar-link-active' : ''}`
            }
          >
            <Icon size={18} strokeWidth={2} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* User pill */}
      {user && (
        <div className="sidebar-user">
          <div className="sidebar-avatar">
            {user.full_name?.charAt(0)?.toUpperCase() || 'A'}
          </div>
          <div className="sidebar-user-info">
            <span className="sidebar-user-name">{user.full_name}</span>
            <span className="sidebar-user-role">{user.role}</span>
          </div>
        </div>
      )}
    </aside>
  );
};
