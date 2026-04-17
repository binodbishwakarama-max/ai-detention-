import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { ElevatedCard } from '../../components/ui/ElevatedCard';
import { Button } from '../../components/ui/Button';
import { Shield } from 'lucide-react';

export const Register: React.FC = () => {
  const [form, setForm] = useState({
    email: '',
    password: '',
    full_name: '',
    organization_name: '',
  });
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const { register } = useAuth();
  const navigate = useNavigate();

  const update = (field: string) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [field]: e.target.value }));

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await register(form);
      navigate('/');
    } catch (err: unknown) {
      const error = err as { response?: { data?: { detail?: string } } };
      setError(error.response?.data?.detail || 'Registration failed. Check requirements.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', padding: '2rem' }}>
      <ElevatedCard style={{ maxWidth: '420px', width: '100%', padding: '2.5rem' }}>
        <div style={{ textAlign: 'center', marginBottom: '2rem' }}>
          <div style={{
            width: 48, height: 48,
            background: 'var(--google-blue)',
            borderRadius: 'var(--radius-sm)',
            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
            marginBottom: '1rem',
          }}>
            <Shield size={24} color="#ffffff" />
          </div>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, letterSpacing: '-0.02em' }}>
            Create Account
          </h2>
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '0.25rem' }}>
            Set up your organization and admin account
          </p>
        </div>

        {error && <div className="error-banner">{error}</div>}

        <form onSubmit={handleRegister} style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem' }}>
          <div>
            <label style={{ display: 'block', marginBottom: '0.3rem', fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Full Name</label>
            <input className="input-field" value={form.full_name} onChange={update('full_name')} required placeholder="Jane Doe" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.3rem', fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Organization</label>
            <input className="input-field" value={form.organization_name} onChange={update('organization_name')} required placeholder="Acme Corp" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.3rem', fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Email</label>
            <input type="email" className="input-field" value={form.email} onChange={update('email')} required placeholder="admin@acme.com" autoComplete="email" />
          </div>
          <div>
            <label style={{ display: 'block', marginBottom: '0.3rem', fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Password</label>
            <input type="password" className="input-field" value={form.password} onChange={update('password')} required autoComplete="new-password" placeholder="Min 8 chars, upper, lower, digit, special" />
          </div>
          <Button type="submit" disabled={loading} style={{ marginTop: '0.5rem', width: '100%' }}>
            {loading ? 'Creating account…' : 'Register'}
          </Button>
        </form>

        <p style={{ textAlign: 'center', marginTop: '1.5rem', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          Already have an account?{' '}
          <Link to="/login" style={{ color: 'var(--google-blue)', textDecoration: 'none', fontWeight: 600 }}>
            Sign in
          </Link>
        </p>
      </ElevatedCard>
    </div>
  );
};
