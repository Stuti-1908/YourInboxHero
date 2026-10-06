import React, { useState } from 'react';
import { register, resendVerificationEmail, RegistrationError } from '../api/invoice';
import './Login.css'; // Reusing Login CSS for the card style

export const Register = ({ onSwitchToLogin, onViewPricing }: { onSwitchToLogin: () => void, onViewPricing?: () => void }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [companyName, setCompanyName] = useState('');
  const [inviteCode, setInviteCode] = useState('');
  const [showInviteCode, setShowInviteCode] = useState(false);
  const [error, setError] = useState('');
  const [needsPlan, setNeedsPlan] = useState(false);
  const [loading, setLoading] = useState(false);
  const [registered, setRegistered] = useState(false);
  const [resendStatus, setResendStatus] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setNeedsPlan(false);
    try {
      await register(username, password, companyName, inviteCode);
      setRegistered(true);
    } catch (err: any) {
      setError(err.message || 'Registration failed');
      setNeedsPlan(err instanceof RegistrationError && err.status === 402);
    } finally {
      setLoading(false);
    }
  };

  const handleResend = async () => {
    setResendStatus('Sending...');
    try {
      await resendVerificationEmail(username);
      setResendStatus('If that email is registered and unverified, a new link has been sent.');
    } catch {
      setResendStatus('Something went wrong — please try again in a moment.');
    }
  };

  if (registered) {
    return (
      <div className="login-container fade-in">
        <div className="login-card">
          <div className="login-brand">
            <h1>YourInbox<span>Hero</span></h1>
          </div>
          <h3 style={{ marginTop: 0 }}>Check your email</h3>
          <p style={{ color: 'var(--color-text-light)' }}>
            We've sent a verification link to <strong>{username}</strong>. Click it to activate your account, then sign in.
          </p>
          <div style={{ marginTop: '16px' }}>
            <button type="button" className="btn-login" onClick={handleResend}>
              Resend verification email
            </button>
            {resendStatus && <p style={{ color: 'var(--color-text-light)', fontSize: '0.85rem', marginTop: '8px' }}>{resendStatus}</p>}
          </div>
          <div style={{ marginTop: '20px', textAlign: 'center', fontSize: '0.9rem', color: 'var(--color-text-light)' }}>
            Already verified? <span onClick={onSwitchToLogin} style={{ color: 'var(--color-primary)', cursor: 'pointer', fontWeight: 600 }}>Sign in here</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="login-container fade-in">
      <div className="login-card">
        <div className="login-brand">
          <h1>YourInbox<span>Hero</span></h1>
          <p>Create an account to automate your reminders.</p>
        </div>
        {error && (
          <div className="login-error">
            {error}
            {needsPlan && onViewPricing && (
              <>
                {' '}
                <span onClick={onViewPricing} style={{ textDecoration: 'underline', cursor: 'pointer', fontWeight: 600 }}>
                  View plans
                </span>
              </>
            )}
          </div>
        )}
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
          {showInviteCode ? (
            <div className="login-group">
              <label>Invite Code</label>
              <input
                type="text"
                value={inviteCode}
                onChange={e => setInviteCode(e.target.value)}
                placeholder="Enter your invite code"
              />
            </div>
          ) : (
            <div style={{ marginBottom: '16px', fontSize: '0.85rem' }}>
              <span onClick={() => setShowInviteCode(true)} style={{ color: 'var(--color-text-light)', cursor: 'pointer', textDecoration: 'underline' }}>
                Have an invite code?
              </span>
            </div>
          )}
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
