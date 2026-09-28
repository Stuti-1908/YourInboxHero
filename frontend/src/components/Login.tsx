import React, { useState } from 'react';
import { login } from '../api/invoice';
import './Login.css';

export const Login = ({ onLoginSuccess, onSwitchToRegister }: { onLoginSuccess: () => void, onSwitchToRegister: () => void }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await login(username, password);
      onLoginSuccess();
    } catch (err: any) {
      setError(err.message || 'Login failed');
    }
  };

  return (
    <div className="login-container fade-in">
      <div className="login-card">
        <div className="login-brand">
          <h1>YourInbox<span>Hero</span></h1>
          <p>Sign in to manage your automated reminders.</p>
        </div>
        {error && <div className="login-error">{error}</div>}
        <form onSubmit={handleSubmit} className="login-form">
          <div className="login-group">
            <label>Username</label>
            <input 
              type="text" 
              value={username} 
              onChange={e => setUsername(e.target.value)} 
              required 
              placeholder="Enter your username"
            />
          </div>
          <div className="login-group">
            <label>Password</label>
            <input 
              type="password" 
              value={password} 
              onChange={e => setPassword(e.target.value)} 
              required 
              placeholder="Enter your password"
            />
          </div>
          <button type="submit" className="btn-login">Sign In</button>
        </form>
        <div style={{ marginTop: '20px', textAlign: 'center', fontSize: '0.9rem', color: 'var(--color-text-light)' }}>
          Don't have an account? <span onClick={onSwitchToRegister} className="switch-auth-link" style={{ color: 'var(--color-primary)', cursor: 'pointer', fontWeight: 600 }}>Sign up</span>
        </div>
      </div>
    </div>
  );
};
