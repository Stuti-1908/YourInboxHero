import React, { useState, useRef } from 'react';
import { previewInvoiceImport, commitInvoiceImport } from '../api/invoice';
import type { ImportPreviewResponse, ImportCommitResponse } from '../api/invoice';
import './Forms.css';

export const ImportInvoices = ({ onSuccess }: { onSuccess: () => void }) => {
  const [preview, setPreview] = useState<ImportPreviewResponse | null>(null);
  const [result, setResult] = useState<ImportCommitResponse | null>(null);
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
      const data = await previewInvoiceImport(file);
      setPreview(data);
    } catch (err: any) {
      setError(err.message || 'Failed to parse CSV file');
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
      const data = await commitInvoiceImport(preview.valid_rows);
      setResult(data);
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

  return (
    <div className="form-card fade-in">
      <div className="form-header">
        <h3>Import Debtors &amp; Invoices from CSV</h3>
      </div>

      {!preview && !result && (
        <>
          <p style={{ color: 'var(--color-text-light)', marginBottom: '16px' }}>
            Upload a CSV file with one row per invoice. Required columns: <code>debtor_name</code>, <code>debtor_email</code>,{' '}
            <code>invoice_number</code>, <code>amount</code>, <code>due_date</code> (YYYY-MM-DD). Optional: <code>debtor_phone</code>,{' '}
            <code>description</code>.
          </p>
          <div className="form-group">
            <input ref={fileInputRef} type="file" accept=".csv" onChange={handleFileChange} disabled={loading} />
          </div>
          {error && <div className="error-message">{error}</div>}
          {loading && <p>Parsing file...</p>}
        </>
      )}

      {preview && (
        <>
          <p>
            <strong>{preview.valid_rows.length}</strong> row(s) ready to import
            {preview.errors.length > 0 && <>, <strong style={{ color: 'var(--color-status-error, #c0392b)' }}>{preview.errors.length}</strong> row(s) with errors (will be skipped)</>}.
          </p>

          {preview.errors.length > 0 && (
            <div style={{ marginBottom: '16px' }}>
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
            <div style={{ marginBottom: '16px', maxHeight: '400px', overflowY: 'auto' }}>
              <table className="modern-table">
                <thead>
                  <tr>
                    <th>Row</th><th>Debtor</th><th>Email</th><th>Invoice #</th><th>Amount</th><th>Due Date</th>
                  </tr>
                </thead>
                <tbody>
                  {preview.valid_rows.map(r => (
                    <tr key={r.row_number}>
                      <td>{r.row_number}</td>
                      <td>{r.debtor_name}{r.debtor_exists && <span style={{ color: 'var(--color-text-light)', fontSize: '0.8rem' }}> (existing)</span>}</td>
                      <td>{r.debtor_email}</td>
                      <td>{r.invoice_number}</td>
                      <td>${r.amount.toFixed(2)}</td>
                      <td>{r.due_date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {error && <div className="error-message">{error}</div>}

          <div className="form-actions">
            <button type="button" className="btn-primary" onClick={handleCommit} disabled={loading || preview.valid_rows.length === 0}>
              {loading ? 'Importing...' : `Import ${preview.valid_rows.length} Row(s)`}
            </button>
            <button type="button" className="btn-action" onClick={handleReset} disabled={loading} style={{ marginLeft: '8px' }}>
              Cancel
            </button>
          </div>
        </>
      )}

      {result && (
        <>
          <p>
            <strong style={{ color: 'var(--color-status-paid, #2e7d32)' }}>{result.created_count}</strong> created,{' '}
            <strong>{result.skipped_count}</strong> skipped,{' '}
            <strong style={{ color: result.error_count > 0 ? 'var(--color-status-error, #c0392b)' : undefined }}>{result.error_count}</strong> error(s).
          </p>
          <div style={{ marginBottom: '16px', maxHeight: '400px', overflowY: 'auto' }}>
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
          <div className="form-actions">
            <button type="button" className="btn-primary" onClick={onSuccess}>
              Done — View Invoices
            </button>
            <button type="button" className="btn-action" onClick={handleReset} style={{ marginLeft: '8px' }}>
              Import Another File
            </button>
          </div>
        </>
      )}
    </div>
  );
};
