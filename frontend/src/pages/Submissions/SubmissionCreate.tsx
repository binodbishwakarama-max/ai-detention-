import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { ArrowLeft, Save } from 'lucide-react';
import { submissionsApi } from '../../api/endpoints';
import { ElevatedCard } from '../../components/ui/ElevatedCard';
import { Button } from '../../components/ui/Button';
import toast from 'react-hot-toast';

const submissionSchema = z.object({
  startup_name: z.string().min(2, 'Name is too short'),
  description: z.string().min(10, 'Description should be more detailed'),
  website_url: z.string().url('Invalid URL').optional().or(z.literal('')),
  pitch_deck_url: z.string().url('Invalid URL').optional().or(z.literal('')),
});

type SubmissionForm = z.infer<typeof submissionSchema>;

export const SubmissionCreate: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<SubmissionForm>({
    resolver: zodResolver(submissionSchema),
  });

  const mutation = useMutation({
    mutationFn: (data: SubmissionForm) => submissionsApi.create(data),
    onSuccess: (res) => {
      toast.success('Submission created successfully!');
      queryClient.invalidateQueries({ queryKey: ['submissions'] });
      navigate(`/submissions/${res.data.id}`);
    },
    onError: () => {
      toast.error('Failed to create submission.');
    },
  });

  return (
    <div className="animate-in">
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button className="btn btn-ghost" onClick={() => navigate('/submissions')} style={{ padding: '0.5rem' }}>
            <ArrowLeft size={18} />
          </button>
          <div>
            <h2 className="page-title">New Submission</h2>
            <p className="page-subtitle">Add a new startup to the evaluation pipeline</p>
          </div>
        </div>
      </div>

      <div style={{ maxWidth: '800px' }}>
        <ElevatedCard>
          <form onSubmit={handleSubmit((data) => mutation.mutate(data))} style={{ display: 'flex', flexDirection: 'column', gap: '1.5rem' }}>
            <div className="form-group">
              <label className="form-label">Startup Name</label>
              <input
                {...register('startup_name')}
                className={`form-input ${errors.startup_name ? 'error' : ''}`}
                placeholder="e.g. Acme AI"
              />
              {errors.startup_name && <p className="form-error">{errors.startup_name.message}</p>}
            </div>

            <div className="form-group">
              <label className="form-label">Elevator Pitch / Description</label>
              <textarea
                {...register('description')}
                className={`form-input ${errors.description ? 'error' : ''}`}
                placeholder="Describe what the startup does in a few sentences..."
                rows={4}
              />
              {errors.description && <p className="form-error">{errors.description.message}</p>}
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <div className="form-group">
                <label className="form-label">Website URL</label>
                <input
                  {...register('website_url')}
                  className={`form-input ${errors.website_url ? 'error' : ''}`}
                  placeholder="https://example.com"
                />
                {errors.website_url && <p className="form-error">{errors.website_url.message}</p>}
              </div>

              <div className="form-group">
                <label className="form-label">Pitch Deck URL (Optional)</label>
                <input
                  {...register('pitch_deck_url')}
                  className={`form-input ${errors.pitch_deck_url ? 'error' : ''}`}
                  placeholder="Link to PDF or Doc"
                />
                {errors.pitch_deck_url && <p className="form-error">{errors.pitch_deck_url.message}</p>}
              </div>
            </div>

            <div style={{ marginTop: '1rem', display: 'flex', gap: '1rem' }}>
              <Button 
                type="submit" 
                variant="primary" 
                disabled={mutation.isPending}
                style={{ flex: 1 }}
              >
                <Save size={18} /> {mutation.isPending ? 'Creating...' : 'Create Submission'}
              </Button>
              <Button 
                type="button" 
                variant="secondary" 
                onClick={() => navigate('/submissions')}
                disabled={mutation.isPending}
              >
                Cancel
              </Button>
            </div>
          </form>
        </ElevatedCard>
      </div>
    </div>
  );
};
