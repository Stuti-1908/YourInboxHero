import { useState } from 'react';
import { createDocumentClient } from '../api/invoice';

export const CreateDocumentClient = ({ onSuccess }: { onSuccess: () => void }) => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    try {
      await createDocumentClient({
        name,
        email,
        phone: phone || undefined
      });
      onSuccess();
    } catch (err: any) {
      setError(err.message || 'Failed to create document client');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card">
      <div className="card-header">
        <h2 className="card-title">Add Document Client</h2>
      </div>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {error && <div style={{ color: 'red', marginBottom: '10px' }}>{error}</div>}
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <label style={{ fontWeight: 600 }}>Name</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Client Name or Business"
            required
            style={{ padding: '10px', borderRadius: '6px', border: '1px solid var(--color-border)' }}
          />
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <label style={{ fontWeight: 600 }}>Email</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="client@example.com"
            required
            style={{ padding: '10px', borderRadius: '6px', border: '1px solid var(--color-border)' }}
          />
        </div>
        
        <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <label style={{ fontWeight: 600 }}>Phone (Optional)</label>
          <input
            type="text"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
            placeholder="+1234567890"
            style={{ padding: '10px', borderRadius: '6px', border: '1px solid var(--color-border)' }}
          />
        </div>
        
        <button
          type="submit"
          disabled={loading}
          style={{
            marginTop: '10px',
            padding: '12px',
            borderRadius: '6px',
            border: 'none',
            background: 'var(--color-primary)',
            color: 'white',
            fontWeight: 600,
            cursor: loading ? 'not-allowed' : 'pointer'
          }}
        >
          {loading ? 'Saving...' : 'Save Client'}
        </button>
      </form>
    </div>
  );
};
