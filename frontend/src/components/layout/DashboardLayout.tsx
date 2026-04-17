import React from 'react';
import { Outlet } from 'react-router-dom';
import { LogOut, Bell } from 'lucide-react';
import { Sidebar } from './Sidebar';
import { useAuth } from '../../context/AuthContext';

export const DashboardLayout: React.FC = () => {
  const { logout } = useAuth();

  return (
    <div className="dashboard-shell">
      <Sidebar />

      <div className="dashboard-main">
        {/* Top bar */}
        <header className="topbar">
          <div className="topbar-left">
            <div className="topbar-status">
              <span className="status-dot" />
              <span className="topbar-status-text">System Online</span>
            </div>
          </div>

          <div className="topbar-right">
            <button className="topbar-icon-btn" title="Notifications">
              <Bell size={18} />
            </button>
          </div>
        </header>

        {/* Route content */}
        <main className="dashboard-content">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
