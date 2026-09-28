import React, { useState, useEffect } from 'react';
import { createInvoice, fetchDebtors } from '../api/invoice';
import type { Debtor } from '../api/invoice';
import './Forms.css';

export const CreateInvoice = ({ onSuccess }: { onSuccess: () => void }) => {
  const [debtors, setDebtors] = useState<Debtor[]>([]);
  const [debtorId, setDebtorId] = useState('');
  const [invoiceNumber, setInvoiceNumber] = useState('');
  const [amount, setAmount] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [description, setDescription] = useState('');
  const [paymentLink, setPaymentLink] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchDebtors()
      .then(data => setDebtors(data))
      .catch(() => setError('Failed to load debtors.'));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    
    if (!debtorId) {
      setError('Please select a debtor.');
      return;
    }

    setLoading(true);
    try {
      await createInvoice({
        debtor_id: debtorId,
        invoice_number: invoiceNumber,
        amount: parseFloat(amount),
        due_date: dueDate,
        description,
        payment_link: paymentLink || undefined
      });
      setDebtorId('');
      setInvoiceNumber('');
      setAmount('');
      setDueDate('');
      setDescription('');
      setPaymentLink('');
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
          <label>Select Debtor</label>
          <select 
            value={debtorId} 
            onChange={(e) => setDebtorId(e.target.value)} 
            required 
            className="form-select"
          >
            <option value="" disabled>-- Select a Debtor --</option>
            {debtors.map(d => (
              <option key={d.id} value={d.id}>{d.name} ({d.email})</option>
            ))}
          </select>
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
        <div className="form-group">
          <label>Payment Link (Optional)</label>
          <input type="url" value={paymentLink} onChange={(e) => setPaymentLink(e.target.value)} placeholder="https://buy.stripe.com/..." />
          <small style={{ color: 'var(--color-text-light)', fontSize: '0.8rem', marginTop: '4px', display: 'block' }}>Add a payment link (e.g. Stripe, Square) to include in reminders.</small>
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
