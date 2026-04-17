import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Rocket, Plus, Filter, ArrowRight } from 'lucide-react';
import { submissionsApi } from '../../api/endpoints';
import { ElevatedCard } from '../../components/ui/ElevatedCard';
import { Button } from '../../components/ui/Button';
import type { SubmissionStatus } from '../../types';

const STATUS_OPTIONS: Array<{ label: string; value: SubmissionStatus | '' }> = [
  { label: 'All', value: '' },
  { label: 'Draft', value: 'draft' },
  { label: 'Submitted', value: 'submitted' },
  { label: 'Under Review', value: 'under_review' },
  { label: 'Evaluated', value: 'evaluated' },
];

const statusBadge = (status: string) => {
  const statusLabels: Record<string, string> = {
    draft: 'Draft',
    submitted: 'Submitted',
    under_review: 'Review',
    evaluated: 'Evaluated',
    archived: 'Archived',
  };
  return <span className={`badge badge-${status}`}>{statusLabels[status] || status}</span>;
};

export const SubmissionsList: React.FC = () => {
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [statusFilter, setStatusFilter] = useState<string>('');
  const pageSize = 15;

  const { data, isLoading } = useQuery({
    queryKey: ['submissions', 'list', page, statusFilter],
    queryFn: () =>
      submissionsApi.list({
        page,
        page_size: pageSize,
        ...(statusFilter ? { status: statusFilter } : {}),
      }),
    select: (res) => res.data,
  });

  const submissions = data?.items ?? [];
  const totalPages = data?.total_pages ?? 1;

  return (
    <div className="animate-in">
      <div className="page-header" style={{ marginBottom: '2rem' }}>
        <div>
          <h2 className="page-title">Submissions</h2>
          <p className="page-subtitle">
            Manage startup applications and trigger evaluations
          </p>
        </div>
        <Button 
          variant="primary" 
          onClick={() => navigate('/submissions/new')}
          style={{ gap: '0.5rem' }}
        >
          <Plus size={18} /> New Submission
        </Button>
      </div>

      <div className="filter-chip-group" style={{ marginBottom: '1.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
          <Filter size={16} color="var(--text-muted)" />
          <div style={{ display: 'flex', gap: '0.5rem', overflowX: 'auto', padding: '4px' }}>
            {STATUS_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                className={statusFilter === opt.value ? 'chip chip-active' : 'chip'}
                onClick={() => { setStatusFilter(opt.value); setPage(1); }}
              >
                {opt.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <ElevatedCard>
        {isLoading ? (
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '4rem 0', gap: '1rem' }}>
            <div className="spinner" />
            <p style={{ color: 'var(--text-muted)' }}>Loading submissions…</p>
          </div>
        ) : submissions.length === 0 ? (
          <div className="empty-state" style={{ textAlign: 'center', padding: '5rem 0' }}>
            <div style={{ width: 64, height: 64, background: 'var(--bg-tertiary)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1.5rem' }}>
              <Rocket size={32} color="var(--text-muted)" />
            </div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>No submissions found</h3>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>Start by adding your first startup application to the pipeline.</p>
            <Button 
              variant="primary"
              onClick={() => navigate('/submissions/new')}
            >
              Add Submission
            </Button>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>Startup Name</th>
                <th>Status</th>
                <th>Submitted</th>
                <th>Website</th>
                <th style={{ width: 48 }}></th>
              </tr>
            </thead>
            <tbody>
              {submissions.map((sub) => (
                <tr
                  key={sub.id}
                  onClick={() => navigate(`/submissions/${sub.id}`)}
                >
                  <td style={{ fontWeight: 500 }}>{sub.startup_name}</td>
                  <td>{statusBadge(sub.status)}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>
                    {new Date(sub.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
                  </td>
                  <td>
                    {sub.website_url ? (
                      <span className="link-text">
                        {sub.website_url.replace(/^https?:\/\//, '')}
                      </span>
                    ) : (
                      <span style={{ color: 'var(--text-muted)' }}>—</span>
                    )}
                  </td>
                  <td>
                    <div className="action-circle">
                      <ArrowRight size={14} />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {totalPages > 1 && (
          <div className="pagination">
            <Button
              variant="secondary"
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem' }}
            >
              Previous
            </Button>
            <div className="pagination-info">
              Page {page} of {totalPages}
            </div>
            <Button
              variant="secondary"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
              style={{ padding: '0.4rem 0.8rem', fontSize: '0.85rem' }}
            >
              Next
            </Button>
          </div>
        )}
      </ElevatedCard>
    </div>
  );
};
