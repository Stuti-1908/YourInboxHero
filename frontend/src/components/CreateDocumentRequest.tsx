import React, { useState, useEffect } from 'react';
import { createDocumentBatch, getDocumentClients } from '../api/invoice';
import type { DocumentClient } from '../api/invoice';
import './Forms.css';

const QUICK_TEMPLATES = [
  'W-9 Tax Form',
  'Signed Contract',
  'Insurance Certificate',
  'ID Verification',
  'Business License',
  'Bank Statement'
];

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

export const CreateDocumentRequest = ({ onSuccess }: { onSuccess: (message: string) => void }) => {
  const [clients, setClients] = useState<DocumentClient[]>([]);
  const [clientsLoaded, setClientsLoaded] = useState(false);
  const [mode, setMode] = useState<'existing' | 'new'>('existing');
  const [clientId, setClientId] = useState('');
  const [newClient, setNewClient] = useState({ name: '', email: '', phone: '', voice_call_consent: false });
  const [dueDate, setDueDate] = useState('');
  const [documents, setDocuments] = useState<string[]>(['']);
  const [note, setNote] = useState('');

  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    getDocumentClients()
      .then(data => {
        setClients(data);
        if (data.length === 0) setMode('new');
      })
      .catch(() => setError('Failed to load clients.'))
      .finally(() => setClientsLoaded(true));
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');

    const validDocs = documents.map(d => d.trim()).filter(Boolean);

    if (mode === 'existing' && !clientId) {
      setError('Please select a client.');
      return;
    }
    if (mode === 'new' && (!newClient.name.trim() || !newClient.email.trim())) {
      setError('Enter the client\'s name and email.');
      return;
    }
    if (mode === 'new' && newClient.voice_call_consent && !newClient.phone.trim()) {
      setError('A phone number is required to record voice call consent.');
      return;
    }
    if (!dueDate) {
      setError('Please select a due date.');
      return;
    }
    if (validDocs.length === 0) {
      setError('Please add at least one document.');
      return;
    }

    setLoading(true);
    try {
      const result = await createDocumentBatch({
        ...(mode === 'existing'
          ? { client_id: clientId }
          : {
              client: {
                name: newClient.name.trim(),
                email: newClient.email.trim(),
                phone: newClient.phone.trim() || undefined,
                voice_call_consent: newClient.voice_call_consent,
              },
            }),
        titles: validDocs,
        description: note.trim() || undefined,
        due_date: dueDate,
      });
      const count = result.requests.length;
      onSuccess(
        result.email_sent
          ? `Requested ${count} document${count === 1 ? '' : 's'} from ${result.client_name}. One email with the upload link${count === 1 ? '' : 's'} was sent to ${result.client_email}.`
          : `Requested ${count} document${count === 1 ? '' : 's'} from ${result.client_name}, but the email could not be sent. Use "Copy Link" in the list below to share the upload link${count === 1 ? '' : 's'} manually.`
      );
    } catch (err: any) {
      setError(err.message || 'Failed to create document request');
    } finally {
      setLoading(false);
    }
  };

  const handleQuickTemplate = (t: string) => {
    setDocuments(prev => {
      if (prev.some(d => d.trim().toLowerCase() === t.toLowerCase())) return prev;
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

  const segmentStyle = (active: boolean): React.CSSProperties => ({
    padding: '8px 16px',
    border: 'none',
    cursor: 'pointer',
    fontWeight: 600,
    fontSize: '0.85rem',
    backgroundColor: active ? 'var(--color-primary)' : 'transparent',
    color: active ? '#fff' : 'var(--color-text)',
  });

  return (
    <div className="form-card fade-in">
      <div className="form-header">
        <h3>New document request</h3>
        <p style={{ color: 'var(--color-text-light)', margin: 0, fontSize: '0.9rem' }}>
          Pick a client (or add a new one) and list the documents you need. They get one email with a private upload link for each document.
        </p>
      </div>
      {error && <div className="error-message">{error}</div>}

      <form onSubmit={handleSubmit}>
        <div className="form-group" style={{ marginBottom: '20px' }}>
          <label>Client *</label>
          <div style={{ display: 'inline-flex', borderRadius: '8px', overflow: 'hidden', border: '1px solid var(--color-border)', marginBottom: '12px', maxWidth: '100%' }}>
            <button type="button" style={segmentStyle(mode === 'existing')} onClick={() => setMode('existing')} disabled={clientsLoaded && clients.length === 0}>
              Existing client
            </button>
            <button type="button" style={{ ...segmentStyle(mode === 'new'), borderLeft: '1px solid var(--color-border)' }} onClick={() => setMode('new')}>
              New client
            </button>
          </div>

          {mode === 'existing' ? (
            <select
              value={clientId}
              onChange={(e) => setClientId(e.target.value)}
              className="form-select"
            >
              <option value="" disabled>-- Select a client --</option>
              {clients.map(c => (
                <option key={c.id} value={c.id}>{c.name} ({c.email})</option>
              ))}
            </select>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(min(220px, 100%), 1fr))', gap: '12px' }}>
              <input
                className="form-input"
                placeholder="Client name *"
                value={newClient.name}
                onChange={(e) => setNewClient({ ...newClient, name: e.target.value })}
              />
              <input
                className="form-input"
                type="email"
                placeholder="Client email *"
                value={newClient.email}
                onChange={(e) => setNewClient({ ...newClient, email: e.target.value })}
              />
              <input
                className="form-input"
                type="tel"
                placeholder="Phone (optional, for SMS/voice)"
                value={newClient.phone}
                onChange={(e) => setNewClient({ ...newClient, phone: e.target.value })}
              />
              <label style={{ display: 'flex', alignItems: 'flex-start', gap: '8px', fontSize: '0.85rem', fontWeight: 400, gridColumn: '1 / -1' }}>
                <input
                  type="checkbox"
                  checked={newClient.voice_call_consent}
                  onChange={(e) => setNewClient({ ...newClient, voice_call_consent: e.target.checked })}
                  style={{ marginTop: '3px' }}
                />
                The client has agreed to receive automated calls and texts at this number.
              </label>
              <small style={{ color: 'var(--color-text-light)', gridColumn: '1 / -1' }}>
                If a client with this email already exists, the request is added to them instead of creating a duplicate.
              </small>
            </div>
          )}
        </div>

        <div className="form-group" style={{ marginBottom: '20px' }}>
          <label>Due date *</label>
          <input type="date" value={dueDate} min={todayIso()} onChange={(e) => setDueDate(e.target.value)} required className="form-input" />
        </div>

        <div style={{ marginBottom: '16px' }}>
          <label style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', marginBottom: '8px', display: 'block' }}>Quick add:</label>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
            {QUICK_TEMPLATES.map(t => (
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
                  color: 'var(--color-text)',
                  cursor: 'pointer'
                }}
              >
                + {t}
              </button>
            ))}
          </div>
        </div>

        <div className="form-group" style={{ marginBottom: '8px' }}>
          <label>Documents needed *</label>
          {documents.map((doc, index) => (
            <div key={index} style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <input
                type="text"
                value={doc}
                onChange={(e) => updateDoc(index, e.target.value)}
                placeholder="e.g. 2024 W-2, Prior year return"
                className="form-input"
                maxLength={200}
                style={{ flex: 1, minWidth: 0, margin: 0 }}
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
                  aria-label="Remove document"
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
          disabled={documents.length >= 20}
          style={{
            color: 'var(--color-primary)',
            background: 'none',
            border: 'none',
            cursor: 'pointer',
            fontWeight: 600,
            padding: '0',
            marginBottom: '24px',
            fontSize: '0.9rem'
          }}
        >
          + Add document
        </button>

        <div className="form-group" style={{ marginBottom: '24px' }}>
          <label>Note for the client (optional)</label>
          <textarea
            className="form-textarea"
            rows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="e.g. Please send the signed copy, not the draft."
          />
        </div>

        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={loading} style={{ width: '100%', padding: '12px' }}>
            {loading ? 'Sending...' : 'Send request'}
          </button>
        </div>
      </form>
    </div>
  );
};
