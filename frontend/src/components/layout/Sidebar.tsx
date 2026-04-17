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
          <Shield size={22} color="currentColor" />
        </div>
        <div>
          <h1 className="sidebar-title">Eval Engine</h1>
          <span className="sidebar-subtitle">AI Validation</span>
        </div>
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
            <Icon size={18} />
            <span>{label}</span>
          </NavLink>
        ))}
      </nav>

      {/* User pill */}
      {user && (
        <div className="sidebar-user">
          <div className="sidebar-avatar">
            {user.full_name?.charAt(0)?.toUpperCase() || 'U'}
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
