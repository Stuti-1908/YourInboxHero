import React, { useState, useEffect } from 'react';
import { createDocumentRequest, getDocumentClients } from '../api/invoice';
import type { DocumentClient } from '../api/invoice';
import './Forms.css';

export const CreateDocumentRequest = ({ onSuccess }: { onSuccess: () => void }) => {
  const [clients, setClients] = useState<DocumentClient[]>([]);
  const [clientId, setClientId] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [documents, setDocuments] = useState<string[]>(['']);
  
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

    const validDocs = documents.map(d => d.trim()).filter(Boolean);

    if (!clientId) {
      setError('Please select a client.');
      return;
    }
    if (!dueDate) {
      setError('Please select a filing deadline (due date).');
      return;
    }
    if (validDocs.length === 0) {
      setError('Please add at least one document title.');
      return;
    }

    setLoading(true);
    try {
      await Promise.all(validDocs.map(title => 
        createDocumentRequest({
          client_id: clientId,
          title,
          due_date: dueDate
        })
      ));
      setClientId('');
      setDueDate('');
      setDocuments(['']);
      onSuccess();
    } catch (err: any) {
      setError(err.message || 'Failed to create document requests');
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
      if (!last.trim()) {
        const newDocs = [...prev];
        newDocs[newDocs.length - 1] = t;
        return newDocs;
      }
      return [...prev, t];
    });
  };

  const updateDoc = (index: number, value: string) => {
    setDocuments(prev => {
      const newDocs = [...prev];
      newDocs[index] = value;
      return newDocs;
    });
  };

  const removeDoc = (index: number) => {
    setDocuments(prev => prev.filter((_, i) => i !== index));
  };

  const addDoc = () => {
    setDocuments(prev => [...prev, '']);
  };

  return (
    <div className="form-card fade-in">
      <div className="form-header">
        <h3>New document request</h3>
        <p style={{ color: 'var(--color-text-secondary)', margin: 0, fontSize: '0.9rem' }}>
          Select the client and exactly which documents you need. They'll get a private link to submit them.
        </p>
      </div>
      {error && <div className="error-message">{error}</div>}
      
      <div style={{ marginBottom: '24px' }}>
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
        <div className="form-group" style={{ marginBottom: '20px' }}>
          <label>Select Client *</label>
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

        <div className="form-group" style={{ marginBottom: '24px' }}>
          <label>Filing deadline *</label>
          <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} required className="form-input" />
        </div>

        <div className="form-group" style={{ marginBottom: '8px' }}>
          <label>Documents needed *</label>
          {documents.map((doc, index) => (
            <div key={index} style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <input 
                type="text" 
                value={doc} 
                onChange={(e) => updateDoc(index, e.target.value)} 
                required={index === 0 && documents.length === 1}
                placeholder="e.g. 2024 W-2, Prior year return" 
                className="form-input"
                style={{ flex: 1, margin: 0 }}
              />
              {documents.length > 1 && (
                <button 
                  type="button" 
                  onClick={() => removeDoc(index)} 
                  style={{ 
                    color: 'var(--color-text-light)', 
                    background: 'none', 
                    border: 'none', 
                    cursor: 'pointer', 
                    fontSize: '1.2rem',
                    padding: '4px 8px'
                  }}
                  title="Remove document"
                >
                  &times;
                </button>
              )}
            </div>
          ))}
        </div>

        <button 
          type="button" 
          onClick={addDoc} 
          style={{ 
            color: 'var(--color-brand-primary)', 
            background: 'none', 
            border: 'none', 
            cursor: 'pointer', 
            fontWeight: 600,
            padding: '0',
            marginBottom: '32px',
            fontSize: '0.9rem'
          }}
        >
          + Add document
        </button>

        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={loading} style={{ width: '100%', padding: '12px' }}>
            {loading ? 'Creating...' : 'Create request'}
          </button>
        </div>
      </form>
    </div>
  );
};
