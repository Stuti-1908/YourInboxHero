import React, { useState } from 'react';
import { createInvoice } from '../api/invoice';
import './Forms.css';

export const CreateInvoice = ({ onSuccess }: { onSuccess: () => void }) => {
  const [debtorId, setDebtorId] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [amount, setAmount] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [description, setDescription] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await createInvoice({
        debtor_id: debtorId,
        invoice_number: invoiceNumber,
        amount: parseFloat(amount),
        due_date: dueDate,
        description
      });
      setDebtorId('');
      setInvoiceNumber('');
      setAmount('');
      setDueDate('');
      setDescription('');
      onSuccess();
    } catch (err: any) {
      setError(err.message || 'Failed to create invoice');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="form-card fade-in">
      <div className="form-header">
        <h3>Add New Invoice</h3>
      </div>
      {error && <div className="error-message">{error}</div>}
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Debtor ID (UUID)</label>
          <input type="text" value={debtorId} onChange={(e) => setDebtorId(e.target.value)} required placeholder="e.g. 123e4567-e89b-12d3-a456-426614174000" />
        </div>
        <div className="form-group">
          <label>Invoice Number</label>
          <input type="text" value={invoiceNumber} onChange={(e) => setInvoiceNumber(e.target.value)} required placeholder="INV-2023-001" />
        </div>
        <div className="form-group">
          <label>Amount ($)</label>
          <input type="number" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} required placeholder="1500.00" />
        </div>
        <div className="form-group">
          <label>Due Date</label>
          <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} required />
        </div>
        <div className="form-group">
          <label>Description (Optional)</label>
          <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Consulting Services" />
        </div>
        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Adding...' : 'Add Invoice'}
          </button>
        </div>
      </form>
    </div>
  );
};
