import React from 'react';
import { useQuery } from "@tanstack/react-query";
import { Plus, BarChart, ArrowRight, Activity } from 'lucide-react';
import { apiClient } from "../../api/client";
import { ElevatedCard } from '../../components/ui/ElevatedCard';
import { Button } from '../../components/ui/Button';
import type { Metric } from "../../types";

async function fetchMetrics(): Promise<Metric[]> {
  const response = await apiClient.get("/metrics");
  return response.data.items;
}

export const MetricsList: React.FC = () => {
  const {
    data: metrics,
    isLoading,
    error,
  } = useQuery({
    queryKey: ["metrics"],
    queryFn: fetchMetrics,
  });

  return (
    <div className="animate-in">
      <div className="page-header" style={{ marginBottom: '2.5rem' }}>
        <div>
          <h2 className="page-title">Metrics</h2>
          <p className="page-subtitle">Configure scoring criteria and performance indicators.</p>
        </div>
        <Button 
          variant="primary"
          style={{ gap: '0.6rem' }}
        >
          <Plus size={18} /> Create Metric
        </Button>
      </div>

      {isLoading ? (
        <div style={{ display: 'flex', justifyContent: 'center', padding: '5rem 0' }}>
          <div className="spinner" />
        </div>
      ) : error ? (
        <div className="error-banner">
          Error fetching metrics: {(error as Error).message}
        </div>
      ) : !metrics?.length ? (
        <ElevatedCard>
          <div className="empty-state" style={{ padding: '5rem 0' }}>
            <div style={{ width: 64, height: 64, background: 'var(--bg-tertiary)', borderRadius: '50%', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 1.5rem' }}>
              <Activity size={32} color="var(--text-muted)" />
            </div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 600, marginBottom: '0.5rem' }}>No metrics defined</h3>
            <p style={{ color: 'var(--text-muted)', marginBottom: '1.5rem' }}>Define how you want to score and evaluate startups.</p>
            <Button variant="secondary">Add Base Metrics</Button>
          </div>
        </ElevatedCard>
      ) : (
        <ElevatedCard>
          <table className="data-table">
            <thead>
              <tr>
                <th>Metric Name</th>
                <th>Type</th>
                <th>Description</th>
                <th style={{ width: 48 }}></th>
              </tr>
            </thead>
            <tbody>
              {metrics.map((metric) => (
                <tr key={metric.id}>
                  <td style={{ fontWeight: 500 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                      <BarChart size={18} color="var(--google-blue)" />
                      {metric.name}
                    </div>
                  </td>
                  <td>
                    <span className="chip" style={{ fontSize: '0.75rem', padding: '0.2rem 0.6rem', textTransform: 'capitalize' }}>
                      {metric.metric_type.replace(/_/g, ' ')}
                    </span>
                  </td>
                  <td style={{ color: 'var(--text-secondary)', maxWidth: 400, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {metric.description}
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
