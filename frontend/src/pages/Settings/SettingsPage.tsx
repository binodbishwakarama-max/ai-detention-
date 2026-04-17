import React from 'react';
import { useQuery } from "@tanstack/react-query";
import { User as UserIcon, Building, Shield, Key, Mail, Fingerprint } from 'lucide-react';
import { apiClient } from "../../api/client";
import { ElevatedCard } from '../../components/ui/ElevatedCard';
import { Button } from '../../components/ui/Button';
import type { User } from "../../types";

async function fetchUserProfile(): Promise<User> {
  const response = await apiClient.get("/auth/me");
  return response.data;
}

export const SettingsPage: React.FC = () => {
  const {
    data: user,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["userProfile"],
    queryFn: fetchUserProfile,
  });

  return (
    <div className="animate-in">
      <div className="page-header" style={{ marginBottom: '2.5rem' }}>
        <div>
          <h2 className="page-title">Settings</h2>
          <p className="page-subtitle">Configure your personal preferences and organization-wide security.</p>
        </div>
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '10rem 0' }}>
          <div className="spinner" />
        </div>
      ) : error ? (
        <div className="error-banner">
          Error fetching settings: {(error as Error).message}
        </div>
      ) : user && (
        <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: '2rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
            {/* Profile Section */}
            <ElevatedCard>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <UserIcon size={20} color="var(--google-blue)" /> Profile Information
              </h3>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
                <div>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Full Name
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                     <UserIcon size={16} color="var(--text-muted)" />
                     <span style={{ fontSize: '0.95rem', fontWeight: 500 }}>{user.full_name}</span>
                  </div>
                </div>

                <div>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '0.5rem', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                    Email Address
                  </label>
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', padding: '0.75rem', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border-subtle)' }}>
                     <Mail size={16} color="var(--text-muted)" />
                     <span style={{ fontSize: '0.95rem', fontWeight: 500 }}>{user.email}</span>
                  </div>
                </div>
              </div>

              <div style={{ marginTop: '2rem' }}>
                 <Button variant="secondary">Change Password</Button>
              </div>
            </ElevatedCard>

            {/* Organization Settings */}
            <ElevatedCard>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Building size={20} color="var(--google-green)" /> Organization Context
              </h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
                <div>
                  <label style={{ fontSize: '0.75rem', color: 'var(--text-muted)', fontWeight: 600, display: 'block', marginBottom: '0.5rem' }}>
                    Active Organization ID
                  </label>
                  <code style={{ display: 'block', padding: '1rem', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)', fontSize: '0.85rem', border: '1px solid var(--border-subtle)' }}>
                    {user.organization_id}
                  </code>
                </div>

                <div style={{ padding: '1rem', background: 'var(--google-blue-light)', borderRadius: 'var(--radius-md)', display: 'flex', gap: '1rem', alignItems: 'flex-start' }}>
                   <Shield size={20} color="var(--google-blue)" style={{ marginTop: '0.2rem' }} />
                   <div>
                     <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--google-blue)', marginBottom: '0.25rem' }}>Administrative Control</h4>
                     <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: '1.4' }}>
                        Your account has <strong>{user.role}</strong> permissions. Contact your system admin to modify organization-wide settings.
                     </p>
                   </div>
                </div>
              </div>
            </ElevatedCard>
          </div>

          {/* Sidebar / Quick Settings */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
             <ElevatedCard style={{ padding: '1.25rem' }}>
                <h4 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                   <Key size={16} color="var(--google-yellow)" /> API Keys
                </h4>
                <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
                   Manage programmatic access to the evaluation engine.
                </p>
                <Button variant="secondary" style={{ width: '100%' }}>Manage Keys</Button>
             </ElevatedCard>

             <ElevatedCard style={{ padding: '1.25rem' }}>
                <h4 style={{ fontSize: '0.9rem', fontWeight: 600, marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                   <Fingerprint size={16} color="var(--google-red)" /> Security
                </h4>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                   <span style={{ fontSize: '0.85rem' }}>MFA Status</span>
                   <span className={`badge badge-${user.mfa_enabled ? 'completed' : 'failed'}`} style={{ fontSize: '0.7rem' }}>
                      {user.mfa_enabled ? 'Enabled' : 'Disabled'}
                   </span>
                </div>
                <Button variant="secondary" style={{ width: '100%' }}>Advanced Security</Button>
             </ElevatedCard>
          </div>
        </div>
      )}
    </div>
  );
}
