import React, { useEffect, useState } from 'react';
import { fetchInvoices, pauseInvoice, Invoice } from '../api/invoice';
import './InvoiceTable.css';

export const InvoiceTable = () => {
  const [invoices, setInvoices] = useState<Invoice[]>([]);
  const [error, setError] = useState<string>('');

  useEffect(() => {
    fetchInvoices()
      .then(setInvoices)
      .catch(e => setError(e.message));
  }, []);

  const handlePause = async (id: string) => {
    try {
      await pauseInvoice(id);
      setInvoices(prev => prev.map(i => i.id === id ? { ...i, status: 'paused' } : i));
    } catch (e: any) {
      setError(e.message);
    }
  };

  return (
    <div className="invoice-container">
      <h2>Invoices</h2>
      {error && <div className="error-message">{error}</div>}
      <table className="invoice-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Number</th>
            <th>Due Date</th>
            <th>Amount</th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {invoices.map(i => (
            <tr key={i.id}>
              <td title={i.id}>{i.id.substring(0, 8)}...</td>
              <td>{i.invoice_number}</td>
              <td>{i.due_date}</td>
              <td>${i.amount.toFixed(2)}</td>
              <td><span className={`status-badge status-${i.status}`}>{i.status}</span></td>
              <td>
                {(i.status === 'upcoming' || i.status === 'due') && (
                  <button className="btn-pause" onClick={() => handlePause(i.id)}>
                    Pause
                  </button>
                )}
              </td>
            </tr>
          ))}
          {invoices.length === 0 && !error && (
            <tr><td colSpan={6} style={{ textAlign: 'center' }}>No invoices found.</td></tr>
          )}
        </tbody>
      </table>
    </div>
  );
};
