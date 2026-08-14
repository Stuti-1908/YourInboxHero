import React, { useEffect, useState } from 'react';
import { fetchAnalytics, AnalyticsData } from '../api/invoice';
import './AnalyticsDashboard.css';

export const AnalyticsDashboard: React.FC = () => {
  const [data, setData] = useState<AnalyticsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const loadData = async () => {
      try {
        const result = await fetchAnalytics();
        setData(result);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    loadData();
  }, []);

  if (loading) return <div className="analytics-dashboard">Loading analytics...</div>;
  if (error) return <div className="analytics-dashboard" style={{color:'red'}}>Error: {error}</div>;
  if (!data) return null;

  const formatCurrency = (val: number) => {
    return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(val);
  };

  const totalAging = 
    data.aging.current + 
    data.aging.days_30 + 
    data.aging.days_60 + 
    data.aging.days_90_plus;

  const getPercent = (val: number) => totalAging ? (val / totalAging) * 100 : 0;

  const maxMonthly = Math.max(...data.monthly_recovered.map(m => m.amount), 1);

  return (
    <div className="analytics-dashboard">
      <div className="stats-row">
        <div className="stat-card">
          <span className="stat-title">Total Outstanding</span>
          <span className="stat-value">{formatCurrency(data.total_outstanding)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-title">Total Recovered</span>
          <span className="stat-value">{formatCurrency(data.total_recovered)}</span>
        </div>
        <div className="stat-card">
          <span className="stat-title">Recovery Rate</span>
          <span className="stat-value">{data.recovery_rate}%</span>
        </div>
      </div>

      <div className="charts-row">
        <div className="chart-card">
          <h3>Aging Report</h3>
          <div className="aging-bar-container">
            <div className="stacked-bar">
              <div className="bar-segment segment-current" style={{ width: `${getPercent(data.aging.current)}%` }} title={`Current: ${formatCurrency(data.aging.current)}`}></div>
              <div className="bar-segment segment-30" style={{ width: `${getPercent(data.aging.days_30)}%` }} title={`30-59 Days: ${formatCurrency(data.aging.days_30)}`}></div>
              <div className="bar-segment segment-60" style={{ width: `${getPercent(data.aging.days_60)}%` }} title={`60-89 Days: ${formatCurrency(data.aging.days_60)}`}></div>
              <div className="bar-segment segment-90" style={{ width: `${getPercent(data.aging.days_90_plus)}%` }} title={`90+ Days: ${formatCurrency(data.aging.days_90_plus)}`}></div>
            </div>
            <div className="aging-legend">
              <div className="legend-item"><div className="legend-color segment-current"></div>Current ({formatCurrency(data.aging.current)})</div>
              <div className="legend-item"><div className="legend-color segment-30"></div>30-59 ({formatCurrency(data.aging.days_30)})</div>
              <div className="legend-item"><div className="legend-color segment-60"></div>60-89 ({formatCurrency(data.aging.days_60)})</div>
              <div className="legend-item"><div className="legend-color segment-90"></div>90+ ({formatCurrency(data.aging.days_90_plus)})</div>
            </div>
          </div>
        </div>

        <div className="chart-card">
          <h3>Status Breakdown</h3>
          <div className="status-breakdown">
            {Object.entries(data.status_breakdown).map(([status, count]) => (
              <div className="status-row" key={status}>
                <span className="status-name">{status}</span>
                <span className="status-count">{count}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="chart-card">
          <h3>Monthly Recovery Trend</h3>
          <div className="monthly-chart">
            {data.monthly_recovered.map((item, idx) => (
              <div className="monthly-bar-wrapper" key={idx}>
                <span className="monthly-value">${item.amount}</span>
                <div 
                  className="monthly-bar" 
                  style={{ height: `${(item.amount / maxMonthly) * 100}%` }}
                  title={`${item.month}: ${formatCurrency(item.amount)}`}
                ></div>
                <span className="monthly-label">{item.month}</span>
              </div>
            ))}
            {data.monthly_recovered.length === 0 && (
              <div style={{ color: 'var(--color-text-muted)', margin: 'auto' }}>No recovery data yet</div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
