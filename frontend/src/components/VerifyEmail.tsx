import { useState, useEffect } from 'react';
import { useSearchParams, useNavigate } from 'react-router-dom';
import { verifyEmail } from '../api/invoice';
import './Login.css';

export const VerifyEmail = () => {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const [status, setStatus] = useState<'verifying' | 'success' | 'error'>('verifying');
  const [message, setMessage] = useState('');

  useEffect(() => {
    const token = searchParams.get('token');
    if (!token) {
      setStatus('error');
      setMessage('No verification token found in this link.');
      return;
    }
    verifyEmail(token)
      .then(msg => {
        setStatus('success');
        setMessage(msg);
      })
      .catch(err => {
        setStatus('error');
        setMessage(err.message || 'Verification failed.');
      });
  }, [searchParams]);

  return (
    <div className="login-container fade-in">
      <div className="login-card">
        <div className="login-brand">
          <h1>YourInbox<span>Hero</span></h1>
        </div>
        {status === 'verifying' && <p>Verifying your email...</p>}
        {status === 'success' && (
          <>
            <h3 style={{ marginTop: 0 }}>Email verified</h3>
            <p style={{ color: 'var(--color-text-light)' }}>{message}</p>
            <button type="button" className="btn-login" onClick={() => navigate('/sign-in')}>
              Go to Sign In
            </button>
          </>
        )}
        {status === 'error' && (
          <>
            <div className="login-error">{message}</div>
            <p style={{ color: 'var(--color-text-light)', marginTop: '12px' }}>
              The link may have expired or already been used. You can request a new one from the sign-up page.
            </p>
          </>
        )}
      </div>
    </div>
  );
};
