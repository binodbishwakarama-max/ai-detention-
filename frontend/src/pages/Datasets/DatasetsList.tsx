import React from 'react';
import { useQuery } from "@tanstack/react-query";
import { Upload, FileJson, ArrowRight, Database } from 'lucide-react';
import { apiClient } from "../../api/client";
import { ElevatedCard } from '../../components/ui/ElevatedCard';
import { Button } from '../../components/ui/Button';
import type { Dataset } from "../../types";

async function fetchDatasets(): Promise<Dataset[]> {
  const response = await apiClient.get("/datasets");
  return response.data.items;
}

export const DatasetsList: React.FC = () => {
  const {
    data: datasets,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["datasets"],
    queryFn: fetchDatasets,
  });

  return (
    <div className="animate-in">
      <div className="page-header" style={{ marginBottom: '2.5rem' }}>
        <div>
          <h2 className="page-title">Datasets</h2>
          <p className="page-subtitle">Manage evaluation samples and ground-truth data sources.</p>
        </div>
        <Button 
          variant="primary"
          style={{ gap: '0.6rem' }}
        >
          <Upload size={18} /> Upload Dataset
        </Button>
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '5rem 0' }}>
          <div className="spinner" />
        </div>
      ) : error ? (
        <div className="error-banner">
          Error fetching datasets: {(error as Error).message}
        </div>
      ) : !datasets?.length ? (
        <ElevatedCard>
          <div className="empty-state" style={{ padding: '5rem 0' }}>
            <div style={{ width: 64, height: 64, background: 'var(--bg-tertiary)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1.5rem' }}>
              <Database size={32} color="var(--text-muted)" />
            </div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>No datasets available</h3>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>You haven't uploaded any evaluation data yet.</p>
            <Button variant="secondary">Upload Example Dataset</Button>
          </div>
        </ElevatedCard>
      ) : (
        <ElevatedCard>
          <table className="data-table">
            <thead>
              <tr>
                <th>Dataset Name</th>
                <th>Kind</th>
                <th>Records</th>
                <th>Last Modified</th>
                <th style={{ width: 48 }}></th>
              </tr>
            </thead>
            <tbody>
              {datasets.map((dataset) => (
                <tr key={dataset.id}>
                  <td style={{ fontWeight: 500 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <FileJson size={18} color="var(--google-blue)" />
                      {dataset.name}
                    </div>
                  </td>
                  <td>
                    <span className="chip" style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem' }}>
                      JSONL
                    </span>
                  </td>
                  <td style={{ fontWeight: 600, color: 'var(--text-secondary)' }}>
                    {dataset.sample_count}
                  </td>
                  <td style={{ color: 'var(--text-secondary)' }}>
                    {new Date(dataset.created_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })}
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
        </ElevatedCard>
      )}
    </div>
  );
}
