import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import type { Role } from '../../types';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requiredRole?: Role;
}

/**
 * Route guard that checks authentication and optional RBAC.
 * Redirects to /login with return-to state if unauthenticated.
 */
export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children, requiredRole }) => {
  const { isAuthenticated, isLoading, role } = useAuth();
  const location = useLocation();

  if (isLoading) {
    return (
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        gap: '0.75rem',
        color: 'var(--text-secondary)',
      }}>
        <div style={{
          width: 20,
          height: 20,
          border: '2px solid var(--border-color)',
          borderTopColor: 'var(--emerald-500)',
          borderRadius: '50%',
          animation: 'spin 0.8s linear infinite',
        }} />
        Restoring session…
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  // RBAC check
  if (requiredRole) {
    const hierarchy: Record<Role, number> = { viewer: 1, member: 2, admin: 3 };
    const userLevel = hierarchy[role ?? 'viewer'];
    const requiredLevel = hierarchy[requiredRole];

    if (userLevel < requiredLevel) {
      return <Navigate to="/" replace />;
    }
  }

  return <>{children}</>;
};
