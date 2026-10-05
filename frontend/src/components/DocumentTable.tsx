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

  const getStatusBadge = (status: string) => {
    const colors: Record<string, string> = {
      pending: '#f59e0b',
      submitted: '#10b981',
      approved: '#3b82f6',
      overdue: '#ef4444'
    };
    return (
      <span style={{
        padding: '4px 10px',
        borderRadius: '12px',
        fontSize: '0.8rem',
        fontWeight: 600,
        color: '#fff',
        backgroundColor: colors[status] || '#6b7280'
      }}>
        {status.toUpperCase()}
      </span>
    );
  };

  if (loading) return <div className="loading">Loading document requests...</div>;

  return (
    <div className="invoice-table-container fade-in">
      <div className="table-header">
        <h2>Document Requests</h2>
        <p style={{ color: 'var(--color-text-light)' }}>Track documents and forms you're collecting from clients.</p>
      </div>
      
      {docs.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '40px', color: 'var(--color-text-light)' }}>
          No document requests yet. Create one to start collecting documents automatically.
        </div>
      ) : (
        <table className="invoice-table">
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
                  <div style={{ fontSize: '0.85em', color: 'var(--color-text-light)' }}>{doc.client.email}</div>
                </td>
                <td>
                  <strong>{doc.title}</strong>
                  {doc.description && <br />}
                  {doc.description && <small style={{ color: 'var(--color-text-light)' }}>{doc.description}</small>}
                </td>
                <td>{doc.due_date}</td>
                <td>{getStatusBadge(doc.status)}</td>
                <td>
                  <span title={`Tier: ${doc.escalation_tier}`}>
                    {doc.escalation_tier.toUpperCase()}
                  </span>
                  {doc.sms_sent_count > 0 && <small style={{ display: 'block', color: 'var(--color-text-light)' }}>{doc.sms_sent_count} SMS</small>}
                  {doc.voice_call_count > 0 && <small style={{ display: 'block', color: 'var(--color-text-light)' }}>{doc.voice_call_count} calls</small>}
                </td>
                <td>
                  <button
                    onClick={() => {
                      navigator.clipboard.writeText(`${window.location.origin}/upload/${doc.upload_token}`);
                      alert('Upload link copied!');
                    }}
                    style={{ padding: '4px 10px', fontSize: '0.8rem', cursor: 'pointer', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'transparent' }}
                  >
                    Copy Link
                  </button>
                </td>
                <td>
                  {doc.status === 'submitted' || doc.status === 'approved' ? (
                    <button
                      onClick={() => handleDownload(doc)}
                      style={{ padding: '4px 10px', fontSize: '0.8rem', cursor: 'pointer', borderRadius: '6px', border: '1px solid var(--color-border)', background: 'transparent', marginRight: '8px' }}
                    >
                      Download
                    </button>
                  ) : null}
                  <button
                    onClick={() => handleDelete(doc.id)}
                    style={{ padding: '4px 10px', fontSize: '0.8rem', cursor: 'pointer', borderRadius: '6px', border: '1px solid #dc2626', color: '#dc2626', background: 'transparent' }}
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
