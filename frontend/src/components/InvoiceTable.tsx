import { useEffect, useState } from 'react';
import { fetchInvoices, pauseInvoice, resumeInvoice, markInvoicePaid, downloadInvoicePdf } from '../api/invoice';
import type { Invoice } from '../api/invoice';
import './InvoiceTable.css';

export const InvoiceTable = () => {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [error, setError] = useState('');

  // silent=true skips surfacing errors to the user, used for the
  // background poll below so a transient network blip doesn't flash
  // an error banner every 20s -- only the initial mount shows errors.
  const loadInvoices = async (silent = false) => {
    try {
      const data = await fetchInvoices();
      setInvoices(data);
    } catch (err: any) {
      if (!silent) setError(err.message);
    }
  };

  useEffect(() => {
    loadInvoices();
    // Invoice status can change outside this tab's own actions -- the
    // scheduler marking invoices overdue, another team member pausing
    // reminders, or a webhook marking one paid.  Poll every 20s so
    // the table stays current without a manual reload, matching the
    // same interval already used by DocumentTable.
    const interval = setInterval(() => loadInvoices(true), 20000);
    return () => clearInterval(interval);
  }, []);

  const handlePause = async (id: string) => {
    try {
      await pauseInvoice(id);
      setInvoices(prev => prev.map(i => i.id === id ? { ...i, status: 'paused' } : i));
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleResume = async (id: string) => {
    try {
      const { status } = await resumeInvoice(id);
      setInvoices(prev => prev.map(i => i.id === id ? { ...i, status } : i));
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleMarkPaid = async (id: string) => {
    try {
      await markInvoicePaid(id);
      setInvoices(prev => prev.map(i => i.id === id ? { ...i, status: 'paid' } : i));
    } catch (err: any) {
      setError(err.message);
    }
  };

  const getStatusBadgeClass = (status: string) => {
    return `badge status-${status.toLowerCase()}`;
  };

  return (
    <div className="table-container fade-in">
      <div className="table-header">
        <h2>Active Invoices</h2>
      </div>
      {error && <div style={{ color: 'var(--color-status-error)', padding: '20px 32px' }}>{error}</div>}
      <table className="modern-table">
        <thead>
          <tr>
            <th>Invoice Number</th>
            <th>Amount</th>
            <th>Due Date</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {invoices.length === 0 ? (
            <tr>
              <td colSpan={5} style={{ textAlign: 'center', color: 'var(--color-text-muted)', padding: '40px' }}>
                No invoices found. Add an invoice to get started.
              </td>
            </tr>
          ) : (
            invoices.map(invoice => (
              <tr key={invoice.id}>
                <td style={{ fontWeight: 500 }}>{invoice.invoice_number}</td>
                <td>${invoice.amount.toFixed(2)}</td>
                <td>{invoice.due_date}</td>
                <td>
                  <span className={getStatusBadgeClass(invoice.status)}>
                    {invoice.status}
                  </span>
                </td>
                <td>
                  {invoice.status !== 'paid' && (
                    <button
                      className="btn-action"
                      onClick={() => invoice.status === 'paused' ? handleResume(invoice.id) : handlePause(invoice.id)}
                    >
                      {invoice.status === 'paused' ? 'Resume' : 'Pause Reminders'}
                    </button>
                  )}
                  {invoice.status !== 'paid' && (
                    <button
                      className="btn-action"
                      onClick={() => handleMarkPaid(invoice.id)}
                      style={{ marginLeft: '8px' }}
                    >
                      Mark Paid
                    </button>
                  )}
                  <button
                    className="btn-action"
                    onClick={() => downloadInvoicePdf(invoice.id)}
                    style={{ marginLeft: '8px' }}
                  >
                    PDF
                  </button>
                </td>
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};
