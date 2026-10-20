import { useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DocumentTable } from './DocumentTable';
import { CreateDocumentRequest } from './CreateDocumentRequest';
import { ImportDocuments } from './ImportDocuments';
import './Forms.css';

type Panel = 'none' | 'new' | 'import';

export const DocumentsPage = () => {
  const [params, setParams] = useSearchParams();
  const initial: Panel = params.get('new') ? 'new' : params.get('import') ? 'import' : 'none';
  const [panel, setPanel] = useState<Panel>(initial);
  const [refreshKey, setRefreshKey] = useState(0);
  const [notice, setNotice] = useState('');

  const toggle = (next: Panel) => {
    setPanel(panel === next ? 'none' : next);
    setNotice('');
    if (params.toString()) setParams({}, { replace: true });
  };

  const done = (message = '') => {
    setPanel('none');
    if (params.toString()) setParams({}, { replace: true });
    setNotice(message);
    setRefreshKey(k => k + 1);
  };

  return (
    <div className="fade-in">
      <div className="page-header">
        <h2>Documents</h2>
        <div className="page-actions">
          <button className={panel === 'new' ? 'btn-secondary' : 'btn-primary'} onClick={() => toggle('new')}>
            {panel === 'new' ? 'Close' : '+ New request'}
          </button>
          <button className="btn-secondary" onClick={() => toggle('import')}>
            {panel === 'import' ? 'Close import' : 'Import CSV / Excel'}
          </button>
        </div>
      </div>

      {notice && (
        <div className="page-panel" role="status" style={{ padding: '12px 16px', borderRadius: '8px', background: 'var(--color-bg-alt)', color: 'var(--color-text)' }}>
          {notice}
        </div>
      )}
      {panel === 'new' && (
        <div className="page-panel">
          <CreateDocumentRequest onSuccess={done} />
        </div>
      )}
      {panel === 'import' && (
        <div className="page-panel">
          <ImportDocuments onSuccess={() => done()} />
        </div>
      )}

      <DocumentTable key={refreshKey} />
    </div>
  );
};
