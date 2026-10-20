import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DebtorTable } from './DebtorTable';
import { CreateDebtor } from './CreateDebtor';
import './Forms.css';

export const DebtorsPage = () => {
  const [params, setParams] = useSearchParams();
  const [showForm, setShowForm] = useState(Boolean(params.get('new')));
  const [refreshKey, setRefreshKey] = useState(0);

  const toggle = () => {
    setShowForm(s => !s);
    if (params.toString()) setParams({}, { replace: true });
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h2>Debtors</h2>
        <div className="page-actions">
          <button className={showForm ? 'btn-secondary' : 'btn-primary'} onClick={toggle}>
            {showForm ? 'Close' : '+ New debtor'}
          </button>
        </div>
      </div>

      {showForm && (
        <div className="page-panel">
          <CreateDebtor onSuccess={() => { setShowForm(false); if (params.toString()) setParams({}, { replace: true }); setRefreshKey(k => k + 1); }} />
        </div>
      )}

      <DebtorTable key={refreshKey} />
    </div>
  );
};
