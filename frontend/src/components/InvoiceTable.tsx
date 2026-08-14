import React, { useEffect, useState } from 'react';
import { fetchInvoices, pauseInvoice, downloadInvoicePdf } from '../api/invoice';
import type { Invoice } from '../api/invoice';
import './InvoiceTable.css';

export const InvoiceTable = () => {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchInvoices()
      .then(setInvoices)
      .catch(err => setError(err.message));
  }, []);

  const handlePause = async (id: string) => {
    try {
      await pauseInvoice(id);
      setInvoices(prev => prev.map(i => i.id === id ? { ...i, status: 'paused' } : i));
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
                  <button 
                    className="btn-action"
                    onClick={() => handlePause(invoice.id)}
                    disabled={invoice.status === 'paused'}
                  >
                    {invoice.status === 'paused' ? 'Paused' : 'Pause Reminders'}
                  </button>
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
