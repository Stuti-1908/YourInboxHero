import { useEffect, useState } from 'react';
import { fetchReminderHistory, downloadReminderHistoryCsv } from '../api/invoice';
import type { ReminderLogEntry } from '../api/invoice';
import './InvoiceTable.css';

const CHANNEL_LABELS: Record<string, string> = {
  email: 'Email',
  sms: 'SMS',
  voice: 'Voice Call',
};

export const ReminderHistory = () => {
  const [logs, setLogs] = useState<ReminderLogEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');

  const loadHistory = async () => {
    setLoading(true);
    setError('');
    try {
      const data = await fetchReminderHistory({
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      });
      setLogs(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadHistory();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleFilter = (e: React.FormEvent) => {
    e.preventDefault();
    loadHistory();
  };

  const handleExport = async () => {
    try {
      await downloadReminderHistoryCsv({
        start_date: startDate || undefined,
        end_date: endDate || undefined,
      });
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="table-container fade-in">
      <div className="table-header">
        <h2>Reminder History</h2>
      </div>

      <form onSubmit={handleFilter} style={{ display: 'flex', gap: '12px', alignItems: 'flex-end', padding: '0 32px 20px' }}>
        <div className="form-group">
          <label className="form-label">From</label>
          <input type="date" className="form-input" value={startDate} onChange={(e) => setStartDate(e.target.value)} />
        </div>
        <div className="form-group">
          <label className="form-label">To</label>
          <input type="date" className="form-input" value={endDate} onChange={(e) => setEndDate(e.target.value)} />
        </div>
        <button type="submit" className="btn-secondary">Filter</button>
        <button type="button" className="btn-secondary" onClick={handleExport}>Export CSV</button>
      </form>

      {error && <div style={{ color: 'var(--color-status-error)', padding: '0 32px 20px' }}>{error}</div>}

      <table className="modern-table">
        <thead>
          <tr>
            <th>Sent At</th>
            <th>Type</th>
            <th>Item</th>
            <th>Contact</th>
            <th>Channel</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {loading ? (
            <tr>
              <td colSpan={6} style={{ textAlign: 'center', color: 'var(--color-text-muted)', padding: '40px' }}>
                Loading...
              </td>
            </tr>
          ) : logs.length === 0 ? (
            <tr>
              <td colSpan={6} style={{ textAlign: 'center', color: 'var(--color-text-muted)', padding: '40px' }}>
                No reminders have been sent yet.
              </td>
            </tr>
          ) : (
            logs.map(log => (
              <tr key={log.id}>
                <td>{log.sent_at ? new Date(log.sent_at).toLocaleString() : '—'}</td>
                <td>{log.invoice_id ? 'Invoice' : 'Document'}</td>
                <td style={{ fontWeight: 500 }}>{log.item_label}</td>
                <td>{log.contact_name}</td>
                <td>{CHANNEL_LABELS[log.channel] || log.channel}</td>
                <td>
                  <span className={`badge status-${log.status}`}>
                    {log.status}
                  </span>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};
