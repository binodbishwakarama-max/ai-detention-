import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation } from '@tanstack/react-query';
import { ArrowLeft, Play, Trash2, ExternalLink, Globe, FileText, Settings, History, Info } from 'lucide-react';
import { submissionsApi, configsApi } from '../../api/endpoints';
import { ElevatedCard } from '../../components/ui/ElevatedCard';
import { Button } from '../../components/ui/Button';
import toast from 'react-hot-toast';

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

export const SubmissionDetail: React.FC = () => {
  const { submissionId } = useParams<{ submissionId: string }>();
  const navigate = useNavigate();
  const [selectedConfigId, setSelectedConfigId] = useState<string>('');

  const { data: submission, isLoading } = useQuery({
    queryKey: ['submission', submissionId],
    queryFn: () => submissionsApi.get(submissionId!),
    select: (res) => res.data,
    enabled: !!submissionId,
  });

  const { data: configs } = useQuery({
    queryKey: ['configs', 'list'],
    queryFn: () => configsApi.list(1, 100),
    select: (res) => res.data.items,
  });


  const evaluateMutation = useMutation({
    mutationFn: (configId: string) => submissionsApi.evaluate(submissionId!, configId),
    onSuccess: (res) => {
      toast.success('Evaluation triggered!');
      navigate(`/evaluations/${res.data.id}`);
    },
    onError: () => {
      toast.error('Failed to trigger evaluation.');
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => submissionsApi.delete(submissionId!),
    onSuccess: () => {
      toast.success('Submission deleted.');
      navigate('/submissions');
    },
  });

  const handleEvaluate = () => {
    if (!selectedConfigId) {
      toast.error('Please select an evaluation config first.');
      return;
    }
    evaluateMutation.mutate(selectedConfigId);
  };

  if (isLoading) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: '10rem 0' }}>
      <div className="spinner" />
    </div>
  );
  
  if (!submission) return <div className="error-banner">Submission not found.</div>;

  return (
    <div className="animate-in">
      <div className="page-header" style={{ marginBottom: '2.5rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '1.25rem' }}>
          <button 
            className="action-circle" 
            onClick={() => navigate('/submissions')}
            style={{ border: '1px solid var(--border-color)', width: 40, height: 40 }}
          >
            <ArrowLeft size={20} />
          </button>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
              <h2 className="page-title">{submission.startup_name}</h2>
              {statusBadge(submission.status)}
            </div>
            <p className="page-subtitle">
              ID: {submissionId?.substring(0, 12)}… • Created {new Date(submission.created_at).toLocaleDateString(undefined, { month: 'long', day: 'numeric', year: 'numeric' })}
            </p>
          </div>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <Button variant="secondary" onClick={() => {}}>
            <Settings size={16} /> Edit
          </Button>
          <Button variant="secondary" onClick={() => deleteMutation.mutate()} style={{ color: 'var(--google-red)' }}>
            <Trash2 size={16} /> Delete
          </Button>
        </div>
      </div>

      <div className="details-grid" style={{ display: 'grid', gridTemplateColumns: '1.75fr 1fr', gap: '2rem' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          {/* Main Content Section */}
          <ElevatedCard>
            <div style={{ padding: '0.5rem' }}>
              <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <Info size={20} color="var(--google-blue)" /> About startup
              </h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
                <div>
                  <h4 style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: '0.75rem' }}>Description</h4>
                  <p style={{ fontSize: '1rem', lineHeight: '1.6', color: 'var(--text-primary)', whiteSpace: 'pre-wrap' }}>
                    {submission.description || 'No description provided.'}
                  </p>
                </div>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem' }}>
                  {submission.website_url && (
                    <div>
                      <h4 style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: '0.75rem' }}>Official Website</h4>
                      <a href={submission.website_url} target="_blank" rel="noreferrer" className="link-text" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem' }}>
                        <Globe size={16} /> {submission.website_url.replace(/^https?:\/\//, '')} <ExternalLink size={14} />
                      </a>
                    </div>
                  )}
                  {submission.pitch_deck_url && (
                    <div>
                      <h4 style={{ fontSize: '0.75rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 700, marginBottom: '0.75rem' }}>Materials</h4>
                      <a href={submission.pitch_deck_url} target="_blank" rel="noreferrer" className="link-text" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '1rem' }}>
                        <FileText size={16} /> Pitch Deck <ExternalLink size={14} />
                      </a>
                    </div>
                  )}
                </div>
              </div>
            </div>
          </ElevatedCard>

          {/* History Section */}
          <ElevatedCard>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1.5rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <History size={20} color="var(--google-yellow)" /> Evaluation History
            </h3>
            <div className="empty-state" style={{ padding: '3rem 0', background: 'var(--bg-tertiary)', borderRadius: 'var(--radius-md)' }}>
              <p style={{ color: 'var(--text-secondary)', fontSize: '0.95rem' }}>
                No evaluations recorded yet. Run a configuration on the right to start.
              </p>
            </div>
          </ElevatedCard>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '2rem' }}>
          {/* Action Card: Trigger Evaluation */}
          <ElevatedCard style={{ background: 'var(--google-blue-light)', borderColor: 'rgba(26, 115, 232, 0.2)' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 600, marginBottom: '1rem', color: 'var(--google-blue)' }}>Analyze Startup</h3>
            <p style={{ fontSize: '0.9rem', color: 'var(--text-secondary)', marginBottom: '2rem', lineHeight: '1.5' }}>
              Deploy the AI evaluation pipeline to generate metrics, scores, and deep-dive insights for this startup.
            </p>

            <div style={{ marginBottom: '2rem' }}>
              <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-primary)', display: 'block', marginBottom: '0.75rem' }}>Evaluation Pipeline</label>
              <div style={{ position: 'relative' }}>
                <select 
                  value={selectedConfigId} 
                  onChange={(e) => setSelectedConfigId(e.target.value)}
                  className="input-select"
                  style={{ width: '100%' }}
                >
                  <option value="">Select a configuration...</option>
                  {configs?.map(c => (
                    <option key={c.id} value={c.id}>{c.name} (v{c.version})</option>
                  ))}
                </select>
              </div>
            </div>

            <Button 
              variant="primary" 
              style={{ width: '100%', padding: '1.25rem', fontSize: '1rem', fontWeight: 600, gap: '0.75rem' }} 
              disabled={evaluateMutation.isPending}
              onClick={handleEvaluate}
            >
              {evaluateMutation.isPending ? (
                <div className="spinner" style={{ borderTopColor: 'white', width: 18, height: 18 }} />
              ) : (
                <Play size={20} fill="currentColor" />
              )}
              {evaluateMutation.isPending ? 'Processing...' : 'Run Analysis'}
            </Button>
          </ElevatedCard>

          {/* Metadata/Tags */}
          <ElevatedCard>
             <h3 style={{ fontSize: '1rem', fontWeight: 600, marginBottom: '1.25rem' }}>System Metadata</h3>
             {Object.keys(submission.metadata || {}).length === 0 ? (
               <p style={{ fontSize: '0.9rem', color: 'var(--text-muted)', fontStyle: 'italic' }}>No additional metadata.</p>
             ) : (
               <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                 {Object.entries(submission.metadata).map(([k, v]) => (
                   <div key={k} style={{ display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid var(--border-subtle)', paddingBottom: '0.5rem' }}>
                     <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 500 }}>{k}</span>
                     <span style={{ fontSize: '0.8rem', color: 'var(--text-primary)', fontWeight: 600 }}>{String(v)}</span>
                   </div>
                 ))}
               </div>
             )}
          </ElevatedCard>
        </div>
      </div>
    </div>
  );
};
