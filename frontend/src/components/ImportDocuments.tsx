import React, { useState, useRef } from 'react';
import { previewDocumentImport, commitDocumentImport } from '../api/invoice';
import type { DocImportPreviewResponse, DocImportCommitResponse } from '../api/invoice';
import './Forms.css';
import './InvoiceTable.css';

const SAMPLE_CSV =
  'client_name,client_email,document_title,due_date,client_phone,description\n' +
  'Jane Smith,jane@example.com,W-9 Tax Form,2026-12-31,,\n' +
  'Jane Smith,jane@example.com,Signed Contract,2026-12-31,,Please sign every page\n';

export const ImportDocuments = ({ onSuccess }: { onSuccess: () => void }) => {
  const [preview, setPreview] = useState<DocImportPreviewResponse | null>(null);
  const [result, setResult] = useState<DocImportCommitResponse | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setError('');
    setResult(null);
    setLoading(true);
    try {
      setPreview(await previewDocumentImport(file));
    } catch (err: any) {
      setError(err.message || 'Failed to read file');
      setPreview(null);
    } finally {
      setLoading(false);
    }
  };

  const handleCommit = async () => {
    if (!preview || preview.valid_rows.length === 0) return;
    setError('');
    setLoading(true);
    try {
      setResult(await commitDocumentImport(preview.valid_rows));
      setPreview(null);
      if (fileInputRef.current) fileInputRef.current.value = '';
    } catch (err: any) {
      setError(err.message || 'Failed to import rows');
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setPreview(null);
    setResult(null);
    setError('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const downloadSample = () => {
    const url = URL.createObjectURL(new Blob([SAMPLE_CSV], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = 'document-requests-sample.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  const clientCount = preview ? new Set(preview.valid_rows.map(r => r.client_email)).size : 0;

  return (
    <div className="form-card fade-in">
      <div className="form-header">
        <h3>Import document requests</h3>
      </div>

      {!preview && !result && (
        <>
          <p style={{ color: 'var(--color-text-light)', marginBottom: '16px' }}>
            Upload a CSV or Excel (.xlsx) file with one row per document. Required columns: <code>client_name</code>,{' '}
            <code>client_email</code>, <code>document_title</code>, <code>due_date</code> (YYYY-MM-DD). Optional:{' '}
            <code>client_phone</code>, <code>description</code>. Clients are matched by email or created if new, and each
            client gets one email listing all of their documents.{' '}
            <button type="button" onClick={downloadSample} style={{ background: 'none', border: 'none', padding: 0, color: 'var(--color-primary)', cursor: 'pointer', textDecoration: 'underline', font: 'inherit' }}>
              Download a sample file
            </button>
          </p>
          <div className="form-group">
            <input ref={fileInputRef} type="file" accept=".csv,.xlsx" onChange={handleFileChange} disabled={loading} />
          </div>
          {error && <div className="error-message">{error}</div>}
          {loading && <p>Reading file...</p>}
        </>
      )}

      {preview && (
        <>
          <p>
            <strong>{preview.valid_rows.length}</strong> document(s) for <strong>{clientCount}</strong> client(s) ready to request
            {preview.errors.length > 0 && <>, <strong style={{ color: 'var(--color-status-error, #c0392b)' }}>{preview.errors.length}</strong> row(s) with errors (will be skipped)</>}.
          </p>

          {preview.errors.length > 0 && (
            <div className="table-scroll" style={{ marginBottom: '16px' }}>
              <h4 style={{ fontSize: '0.9rem', marginBottom: '8px' }}>Errors</h4>
              <table className="modern-table">
                <thead><tr><th>Row</th><th>Error</th></tr></thead>
                <tbody>
                  {preview.errors.map(e => (
                    <tr key={e.row_number}><td>{e.row_number}</td><td style={{ color: 'var(--color-status-error, #c0392b)' }}>{e.error}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {preview.valid_rows.length > 0 && (
            <div className="table-scroll" style={{ marginBottom: '16px', maxHeight: '400px', overflowY: 'auto' }}>
              <table className="modern-table">
                <thead>
                  <tr><th>Row</th><th>Client</th><th>Email</th><th>Document</th><th>Due</th></tr>
                </thead>
                <tbody>
                  {preview.valid_rows.map(r => (
                    <tr key={r.row_number}>
                      <td>{r.row_number}</td>
                      <td>{r.client_name}{r.client_exists && <span style={{ color: 'var(--color-text-light)', fontSize: '0.8rem' }}> (existing)</span>}</td>
                      <td>{r.client_email}</td>
                      <td>{r.document_title}</td>
                      <td>{r.due_date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {error && <div className="error-message">{error}</div>}

          <div className="form-actions" style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button type="button" className="btn-primary" onClick={handleCommit} disabled={loading || preview.valid_rows.length === 0}>
              {loading ? 'Sending...' : `Request ${preview.valid_rows.length} document(s)`}
            </button>
            <button type="button" className="btn-secondary" onClick={handleReset} disabled={loading}>
              Cancel
            </button>
          </div>
        </>
      )}

      {result && (
        <>
          <p>
            <strong style={{ color: 'var(--color-status-paid, #2e7d32)' }}>{result.created_count}</strong> requested,{' '}
            <strong>{result.skipped_count}</strong> skipped,{' '}
            <strong style={{ color: result.error_count > 0 ? 'var(--color-status-error, #c0392b)' : undefined }}>{result.error_count}</strong> error(s).{' '}
            {result.emails_sent} email(s) sent
            {result.emails_failed > 0 && <>, <strong style={{ color: 'var(--color-status-error, #c0392b)' }}>{result.emails_failed} failed</strong> (use Copy Link in the list to share manually)</>}.
          </p>
          <div className="table-scroll" style={{ marginBottom: '16px', maxHeight: '400px', overflowY: 'auto' }}>
            <table className="modern-table">
              <thead><tr><th>Row</th><th>Status</th><th>Detail</th></tr></thead>
              <tbody>
                {result.results.map(r => (
                  <tr key={r.row_number}>
                    <td>{r.row_number}</td>
                    <td style={{ textTransform: 'capitalize' }}>{r.status}</td>
                    <td>{r.detail}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="form-actions" style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            <button type="button" className="btn-primary" onClick={onSuccess}>Done</button>
            <button type="button" className="btn-secondary" onClick={handleReset}>Import another file</button>
          </div>
        </>
      )}
    </div>
  );
};
