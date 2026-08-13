import React, { useEffect, useState } from 'react';
import { fetchDebtors } from '../api/invoice';
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
          </tr>
        </thead>
        <tbody>
          {debtors.length === 0 ? (
            <tr>
              <td colSpan={4} style={{ textAlign: 'center', color: 'var(--color-text-muted)', padding: '40px' }}>
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
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
};
