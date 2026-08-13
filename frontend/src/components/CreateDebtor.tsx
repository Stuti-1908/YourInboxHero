import React, { useState } from 'react';
import { createDebtor } from '../api/invoice';
import './Forms.css';

export const CreateDebtor = ({ onSuccess }: { onSuccess: () => void }) => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await createDebtor({ name, email, phone, debtor_type: 'business' });
      setName('');
      setEmail('');
      setPhone('');
      onSuccess();
    } catch (err: any) {
      setError(err.message || 'Failed to create debtor');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="form-container">
      <h3>Add New Debtor</h3>
      {error && <div className="error-message">{error}</div>}
      <form onSubmit={handleSubmit}>
        <div className="form-group">
          <label>Company Name</label>
          <input type="text" value={name} onChange={(e) => setName(e.target.value)} required />
        </div>
        <div className="form-group">
          <label>Email Address</label>
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required />
        </div>
        <div className="form-group">
          <label>Phone (Optional)</label>
          <input type="text" value={phone} onChange={(e) => setPhone(e.target.value)} />
        </div>
        <button type="submit" className="btn-primary" disabled={loading}>
          {loading ? 'Adding...' : 'Add Debtor'}
        </button>
      </form>
    </div>
  );
};
