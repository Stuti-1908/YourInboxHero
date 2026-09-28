import React, { useState, useEffect } from 'react';
import { createDocumentRequest, getDocumentClients } from '../api/invoice';
import type { DocumentClient } from '../api/invoice';
import './Forms.css';

export const CreateDocumentRequest = ({ onSuccess }: { onSuccess: () => void }) => {
  const [clients, setClients] = useState<DocumentClient[]>([]);
  const [clientId, setClientId] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [dueDate, setDueDate] = useState('');
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

    setLoading(true);
    try {
      await createDocumentRequest({
        client_id: clientId,
        title,
        description: description || undefined,
        due_date: dueDate
      });
      setClientId('');
      setTitle('');
      setDescription('');
      setDueDate('');
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
              onClick={() => setTitle(t)}
              style={{
                padding: '6px 12px',
                fontSize: '0.8rem',
                borderRadius: '16px',
                border: title === t ? '2px solid var(--color-primary)' : '1px solid var(--color-border)',
                background: title === t ? 'var(--color-bg-alt)' : 'transparent',
                cursor: 'pointer',
                fontWeight: title === t ? 600 : 400
              }}
            >
              {t}
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
        <div className="form-group">
          <label>Document Title</label>
          <input type="text" value={title} onChange={(e) => setTitle(e.target.value)} required placeholder="e.g. W-9 Tax Form" />
        </div>
        <div className="form-group">
          <label>Description (Optional)</label>
          <input type="text" value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Please provide your latest W-9..." />
        </div>
        <div className="form-group">
          <label>Due Date</label>
          <input type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} required />
        </div>
        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Creating...' : 'Create Document Request'}
          </button>
        </div>
      </form>
    </div>
  );
};
