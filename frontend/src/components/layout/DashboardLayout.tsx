import React from 'react';
import { Outlet } from 'react-router-dom';
import { Bell, HelpCircle, Grid } from 'lucide-react';
import { Sidebar } from './Sidebar';

export const DashboardLayout: React.FC = () => {
  return (
    <div className="dashboard-shell">
      <Sidebar />

      <div className="dashboard-main">
        {/* Top bar */}
        <header className="topbar">
          <div className="topbar-status">
            <span className="status-dot" />
            <span className="topbar-status-text">System Online</span>
          </div>

          <div className="topbar-right">
            <button className="topbar-icon-btn" title="Support">
              <HelpCircle size={20} />
            </button>
            <button className="topbar-icon-btn" title="Apps">
              <Grid size={20} />
            </button>
            <button className="topbar-icon-btn" title="Notifications">
              <Bell size={20} />
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
