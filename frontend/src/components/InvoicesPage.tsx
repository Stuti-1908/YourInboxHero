import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { InvoiceTable } from './InvoiceTable';
import { CreateInvoice } from './CreateInvoice';
import { ImportInvoices } from './ImportInvoices';
import './Forms.css';

type Panel = 'none' | 'new' | 'import';

export const InvoicesPage = () => {
  const [params, setParams] = useSearchParams();
  const initial: Panel = params.get('new') ? 'new' : params.get('import') ? 'import' : 'none';
  const [panel, setPanel] = useState<Panel>(initial);
  const [refreshKey, setRefreshKey] = useState(0);

  const toggle = (next: Panel) => {
    setPanel(panel === next ? 'none' : next);
    if (params.toString()) setParams({}, { replace: true });
  };

  const done = () => {
    setPanel('none');
    if (params.toString()) setParams({}, { replace: true });
    setRefreshKey(k => k + 1);
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h2>Invoices</h2>
        <div className="page-actions">
          <button className={panel === 'new' ? 'btn-secondary' : 'btn-primary'} onClick={() => toggle('new')}>
            {panel === 'new' ? 'Close' : '+ New invoice'}
          </button>
          <button className="btn-secondary" onClick={() => toggle('import')}>
            {panel === 'import' ? 'Close import' : 'Import CSV / Excel'}
          </button>
        </div>
      </div>

      {panel === 'new' && (
        <div className="page-panel">
          <CreateInvoice onSuccess={done} />
        </div>
      )}
      {panel === 'import' && (
        <div className="page-panel">
          <ImportInvoices onSuccess={done} />
        </div>
      )}

      <InvoiceTable key={refreshKey} />
    </div>
  );
};
