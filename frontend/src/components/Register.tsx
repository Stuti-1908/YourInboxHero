import React, { useState } from 'react';
import { register } from '../api/invoice';
import './Login.css'; // Reusing Login CSS for the card style

export const Register = ({ onRegisterSuccess, onSwitchToLogin }: { onRegisterSuccess: () => void, onSwitchToLogin: () => void }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await register(username, password, companyName);
      onRegisterSuccess();
    } catch (err: any) {
      setError(err.message || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-container fade-in">
      <div className="login-card">
        <div className="login-brand">
          <h1>YourInbox<span>Hero</span></h1>
          <p>Create an account to automate your reminders.</p>
        </div>
        {error && <div className="login-error">{error}</div>}
        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-group">
            <label>Email Address</label>
            <input 
              type="email" 
              value={username} 
              onChange={e => setUsername(e.target.value)} 
              required 
              placeholder="Enter your email"
            />
          </div>
          <div className="login-group">
            <label>Company Name</label>
            <input 
              type="text" 
              value={companyName} 
              onChange={e => setCompanyName(e.target.value)} 
              required 
              placeholder="Your Business Name"
            />
          </div>
          <div className="login-group">
            <label>Password</label>
            <input 
              type="password" 
              value={password} 
              onChange={e => setPassword(e.target.value)} 
              required 
              placeholder="Choose a strong password"
              minLength={6}
            />
          </div>
          <button type="submit" className="btn-login" disabled={loading}>
            {loading ? 'Creating account...' : 'Sign Up'}
          </button>
        </form>
        <div style={{ marginTop: '20px', textAlign: 'center', fontSize: '0.9rem', color: 'var(--color-text-light)' }}>
          Already have an account? <span onClick={onSwitchToLogin} style={{ color: 'var(--color-primary)', cursor: 'pointer', fontWeight: 600 }}>Sign in here</span>
        </div>
      </div>
    </div>
  );
};
