import { useEffect, useState } from 'react';
import { fetchDebtors, deleteDebtor, updateDebtor } from '../api/invoice';
import type { Debtor } from '../api/invoice';
import './InvoiceTable.css';

export const DebtorTable = () => {
  const [debtors, setDebtors] = useState<Debtor[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    fetchDebtors()
      .then(setDebtors)
      .catch(err => setError(err.message));
  }, []);

  const handleDelete = async (id: string) => {
    if (!window.confirm("Are you sure? This will delete the debtor and all associated invoices and reminders permanently.")) return;
    try {
      await deleteDebtor(id);
      setDebtors(prev => prev.filter(d => d.id !== id));
    } catch (err: any) {
      setError(err.message);
    }
  };

  const handleToggleConsent = async (debtor: Debtor) => {
    const next = !debtor.voice_call_consent;
    try {
      await updateDebtor(debtor.id, { voice_call_consent: next });
      setDebtors(prev => prev.map(d => d.id === debtor.id ? { ...d, voice_call_consent: next } : d));
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="table-container fade-in">
      <div className="table-header">
        <h2>Your Debtors</h2>
      </div>
      {error && <div style={{ color: 'var(--color-status-error)', padding: '20px 32px' }}>{error}</div>}
      <table className="modern-table">
        <thead>
          <tr>
            <th>Company Name</th>
            <th>Email</th>
            <th>Phone</th>
            <th>Type</th>
            <th>Voice Call Consent</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {debtors.length === 0 ? (
            <tr>
              <td colSpan={6} style={{ textAlign: 'center', color: 'var(--color-text-muted)', padding: '40px' }}>
                No debtors found. Add a debtor to get started.
              </td>
            </tr>
          ) : (
            debtors.map(debtor => (
              <tr key={debtor.id}>
                <td style={{ fontWeight: 500 }}>{debtor.name}</td>
                <td>{debtor.email}</td>
                <td>{debtor.phone || 'N/A'}</td>
                <td>
                  <span className="badge status-upcoming">
                    {debtor.debtor_type}
                  </span>
                </td>
                <td>
                  <label style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: debtor.phone ? 'pointer' : 'not-allowed', opacity: debtor.phone ? 1 : 0.5 }}>
                    <input
                      type="checkbox"
                      checked={debtor.voice_call_consent}
                      disabled={!debtor.phone}
                      onChange={() => handleToggleConsent(debtor)}
                    />
                    {debtor.voice_call_consent ? 'Consented' : 'Not consented'}
                  </label>
                </td>
                <td>
                  <button
                    className="btn-action"
                    style={{ borderColor: 'var(--color-status-error)', color: 'var(--color-status-error)' }}
                    onClick={() => handleDelete(debtor.id)}
                  >
                    Delete
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
