import React, { useState, useEffect } from 'react';
import { createDocumentRequest, getDocumentClients } from '../api/invoice';
import type { DocumentClient } from '../api/invoice';
import './Forms.css';

export const CreateDocumentRequest = ({ onSuccess }: { onSuccess: () => void }) => {
  const [clients, setClients] = useState<DocumentClient[]>([]);
  const [clientId, setClientId] = useState('');
  
  const [documents, setDocuments] = useState([{ title: '', description: '', dueDate: '' }]);
  
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getDocumentClients()
      .then(data => setClients(data))
      .catch(() => setError('Failed to load clients.'));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    if (!clientId) {
      setError('Please select a client.');
      return;
    }

    const invalidDocs = documents.some(d => !d.title || !d.dueDate);
    if (invalidDocs) {
      setError('Please fill in all required fields for each document.');
      return;
    }

    setLoading(true);
    try {
      await Promise.all(documents.map(doc => 
        createDocumentRequest({
          client_id: clientId,
          title: doc.title,
          description: doc.description || undefined,
          due_date: doc.dueDate
        })
      ));
      setClientId('');
      setDocuments([{ title: '', description: '', dueDate: '' }]);
      onSuccess();
    } catch (err: any) {
      setError(err.message || 'Failed to create document request');
    } finally {
      setLoading(false);
    }
  };

  const quickTemplates = [
    'W-9 Tax Form',
    'Signed Contract',
    'Insurance Certificate',
    'ID Verification',
    'Business License',
    'Bank Statement'
  ];

  const handleQuickTemplate = (t: string) => {
    setDocuments(prev => {
      const last = prev[prev.length - 1];
      if (!last.title && !last.description && !last.dueDate) {
        const newDocs = [...prev];
        newDocs[newDocs.length - 1] = { ...last, title: t };
        return newDocs;
      }
      return [...prev, { title: t, description: '', dueDate: '' }];
    });
  };

  const updateDoc = (index: number, field: keyof typeof documents[0], value: string) => {
    setDocuments(prev => {
      const newDocs = [...prev];
      newDocs[index] = { ...newDocs[index], [field]: value };
      return newDocs;
    });
  };

  const removeDoc = (index: number) => {
    setDocuments(prev => prev.filter((_, i) => i !== index));
  };

  const addDoc = () => {
    setDocuments(prev => [...prev, { title: '', description: '', dueDate: '' }]);
  };

  return (
    <div className="form-card fade-in">
      <div className="form-header">
        <h3>Request Document</h3>
      </div>
      {error && <div className="error-message">{error}</div>}
      
      <div style={{ marginBottom: '16px' }}>
        <label style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', marginBottom: '8px', display: 'block' }}>Quick Templates:</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
          {quickTemplates.map(t => (
            <button
              key={t}
              type="button"
              onClick={() => handleQuickTemplate(t)}
              style={{
                padding: '6px 12px',
                fontSize: '0.8rem',
                borderRadius: '16px',
                border: '1px solid var(--color-border)',
                background: 'transparent',
                cursor: 'pointer'
              }}
            >
              + {t}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Select Client</label>
          <select
            value={clientId}
            onChange={(e) => setClientId(e.target.value)}
            required
            className="form-select"
            disabled={clients.length === 0}
          >
            <option value="" disabled>-- Select a Client --</option>
            {clients.map(c => (
              <option key={c.id} value={c.id}>{c.name} ({c.email})</option>
            ))}
          </select>
          {clients.length === 0 && <small style={{ color: 'red' }}>Please create a client first.</small>}
        </div>

        {documents.map((doc, index) => (
          <div key={index} style={{ padding: '16px', border: '1px solid var(--color-border)', borderRadius: '8px', marginBottom: '16px', position: 'relative' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
              <h4 style={{ margin: 0, fontSize: '0.9rem' }}>Document {index + 1}</h4>
              {documents.length > 1 && (
                <button type="button" onClick={() => removeDoc(index)} style={{ color: 'red', background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.8rem' }}>
                  Remove
                </button>
              )}
            </div>
            
            <div className="form-group">
              <label>Document Title</label>
              <input type="text" value={doc.title} onChange={(e) => updateDoc(index, 'title', e.target.value)} required placeholder="e.g. W-9 Tax Form" />
            </div>
            <div className="form-group">
              <label>Description (Optional)</label>
              <input type="text" value={doc.description} onChange={(e) => updateDoc(index, 'description', e.target.value)} placeholder="Please provide your latest W-9..." />
            </div>
            <div className="form-group">
              <label>Due Date</label>
              <input type="date" value={doc.dueDate} onChange={(e) => updateDoc(index, 'dueDate', e.target.value)} required />
            </div>
          </div>
        ))}

        <button type="button" onClick={addDoc} className="btn-secondary" style={{ width: '100%', marginBottom: '24px' }}>
          + Add Another Document
        </button>

        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Creating...' : `Create ${documents.length} Document Request${documents.length > 1 ? 's' : ''}`}
          </button>
        </div>
      </form>
    </div>
  );
};
