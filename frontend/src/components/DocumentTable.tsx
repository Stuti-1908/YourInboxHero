import React, { useState, useEffect } from 'react';
import { fetchDocumentRequests, deleteDocumentRequest, downloadDocument } from '../api/invoice';
import type { DocumentRequest } from '../api/invoice';
import './InvoiceTable.css';

export const DocumentTable: React.FC = () => {
  const [docs, setDocs] = useState<DocumentRequest[]>([]);
  const [loading, setLoading] = useState(true);

  const loadDocs = async () => {
    try {
      const data = await fetchDocumentRequests();
      setDocs(data);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { loadDocs(); }, []);

  const handleDelete = async (id: string) => {
    if (!confirm('Are you sure you want to delete this document request?')) return;
    try {
      await deleteDocumentRequest(id);
      setDocs(docs.filter(d => d.id !== id));
    } catch (err) {
      console.error(err);
    }
  };

  const handleDownload = async (doc: DocumentRequest) => {
    try {
      await downloadDocument(doc.id, doc.uploaded_file_name);
    } catch (err: any) {
      alert(err.message || 'Failed to download document');
    }
  };

  const getStatusBadge = (status: string) => (
    <span className={`badge status-${status.toLowerCase()}`}>{status}</span>
  );

  if (loading) return <div className="loading">Loading document requests...</div>;

  return (
    <div className="table-container fade-in">
      <div className="table-header">
        <h2>Document Requests</h2>
        <p style={{ color: 'var(--color-text-secondary)', margin: 0 }}>Track documents and forms you're collecting from clients.</p>
      </div>

      {docs.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--color-text-secondary)' }}>
          No document requests yet. Create one to start collecting documents automatically.
        </div>
      ) : (
        <table className="modern-table">
          <thead>
            <tr>
              <th>Client</th>
              <th>Document</th>
              <th>Due Date</th>
              <th>Status</th>
              <th>Escalation</th>
              <th>Upload Link</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {docs.map(doc => (
              <tr key={doc.id}>
                <td>
                  <div style={{ fontWeight: 500 }}>{doc.client.name}</div>
                  <div style={{ fontSize: '0.85em', color: 'var(--color-text-secondary)' }}>{doc.client.email}</div>
                </td>
                <td>
                  <strong>{doc.title}</strong>
                  {doc.description && <br />}
                  {doc.description && <small style={{ color: 'var(--color-text-secondary)' }}>{doc.description}</small>}
                </td>
                <td>{doc.due_date}</td>
                <td>{getStatusBadge(doc.status)}</td>
                <td>
                  <span title={`Tier: ${doc.escalation_tier}`}>
                    {doc.escalation_tier.toUpperCase()}
                  </span>
                  {doc.sms_sent_count > 0 && <small style={{ display: 'block', color: 'var(--color-text-secondary)' }}>{doc.sms_sent_count} SMS</small>}
                  {doc.voice_call_count > 0 && <small style={{ display: 'block', color: 'var(--color-text-secondary)' }}>{doc.voice_call_count} calls</small>}
                </td>
                <td>
                  <button
                    className="btn-action"
                    onClick={() => {
                      navigator.clipboard.writeText(`${window.location.origin}/upload/${doc.upload_token}`);
                      alert('Upload link copied!');
                    }}
                  >
                    Copy Link
                  </button>
                </td>
                <td style={{ display: 'flex', gap: '8px' }}>
                  {doc.status === 'submitted' || doc.status === 'approved' ? (
                    <button className="btn-action" onClick={() => handleDownload(doc)}>
                      Download
                    </button>
                  ) : null}
                  <button
                    className="btn-action"
                    style={{ borderColor: '#dc2626', color: '#dc2626' }}
                    onClick={() => handleDelete(doc.id)}
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};
