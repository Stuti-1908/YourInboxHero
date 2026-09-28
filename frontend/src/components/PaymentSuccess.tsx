import { useState, useEffect } from 'react';
import './Login.css';

const PLAN_DETAILS: Record<string, { name: string; price: number; chases: number }> = {
  starter: { name: 'Starter', price: 149, chases: 100 },
  growth: { name: 'Growth', price: 299, chases: 300 },
  scale: { name: 'Scale', price: 497, chases: 750 },
};

export const PaymentSuccess = ({
  onGoToRegister,
  onGoToLogin
}: {
  onGoToRegister: () => void;
  onGoToLogin: () => void;
}) => {
  const [plan, setPlan] = useState<string | null>(null);
  const [activating, setActivating] = useState(false);
  const [activated, setActivated] = useState(false);
  const [email, setEmail] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    // Read plan from URL params: /payment-success?plan=growth
    const params = new URLSearchParams(window.location.search);
    const planParam = params.get('plan');
    if (planParam && PLAN_DETAILS[planParam]) {
      setPlan(planParam);
    }
  }, []);

  const handleActivate = async () => {
    if (!email || !plan) return;
    setActivating(true);
    setError('');

    try {
      const res = await fetch('/api/payments/activate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email,
          plan,
          square_transaction_id: new URLSearchParams(window.location.search).get('transactionId') || null
        })
      });

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        if (res.status === 404) {
          setError('Account not found. Please register first, then come back to activate your plan.');
        } else {
          setError(data.detail || 'Failed to activate plan');
        }
        return;
      }

      setActivated(true);
    } catch {
      setError('Connection error. Please try again.');
    } finally {
      setActivating(false);
    }
  };

  const planInfo = plan ? PLAN_DETAILS[plan] : null;

  return (
    <div className="login-page" style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="login-card" style={{ maxWidth: '500px', textAlign: 'center' }}>
        {!activated ? (
          <>
            <div style={{ fontSize: '3rem', marginBottom: '16px' }}>
              {planInfo ? '🎉' : '⚠️'}
            </div>
            <h2 style={{ marginBottom: '8px' }}>
              {planInfo ? 'Payment Successful!' : 'Welcome to YourInboxHero'}
            </h2>
            {planInfo && (
              <div style={{
                background: 'var(--color-bg-alt)',
                border: '1px solid var(--color-border)',
                borderRadius: '12px',
                padding: '20px',
                margin: '20px 0'
              }}>
                <h3 style={{ color: 'var(--color-primary)', margin: '0 0 8px 0' }}>
                  {planInfo.name} Plan
                </h3>
                <p style={{ fontSize: '2rem', fontWeight: 700, margin: '0' }}>
                  ${planInfo.price}<span style={{ fontSize: '1rem', fontWeight: 400 }}>/mo</span>
                </p>
                <p style={{ color: 'var(--color-text-light)', margin: '8px 0 0 0' }}>
                  {planInfo.chases} automated chases/month
                </p>
              </div>
            )}

            <p style={{ color: 'var(--color-text-light)', marginBottom: '20px' }}>
              Enter your account email to activate your subscription.
              {!planInfo && ' If you came from a Square checkout, make sure the URL has ?plan=starter, ?plan=growth, or ?plan=scale'}
            </p>

            {error && (
              <div style={{
                background: '#fef2f2',
                color: '#dc2626',
                padding: '12px',
                borderRadius: '8px',
                marginBottom: '16px',
                fontSize: '0.9rem'
              }}>
                {error}
              </div>
            )}

            <input
              type="email"
              placeholder="Your account email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              style={{
                width: '100%',
                padding: '12px 16px',
                borderRadius: '8px',
                border: '1px solid var(--color-border)',
                fontSize: '1rem',
                marginBottom: '12px',
                boxSizing: 'border-box'
              }}
            />

            <button
              onClick={handleActivate}
              disabled={!email || !plan || activating}
              style={{
                width: '100%',
                padding: '14px',
                borderRadius: '8px',
                border: 'none',
                background: 'var(--color-primary)',
                color: '#fff',
                fontSize: '1rem',
                fontWeight: 600,
                cursor: 'pointer',
                opacity: (!email || !plan || activating) ? 0.6 : 1,
                marginBottom: '16px'
              }}
            >
              {activating ? 'Activating...' : 'Activate My Plan'}
            </button>

            <div style={{ display: 'flex', gap: '12px', justifyContent: 'center' }}>
              <button onClick={onGoToRegister} style={{ background: 'none', border: 'none', color: 'var(--color-primary)', cursor: 'pointer', textDecoration: 'underline' }}>
                Don't have an account? Register
              </button>
              <button onClick={onGoToLogin} style={{ background: 'none', border: 'none', color: 'var(--color-primary)', cursor: 'pointer', textDecoration: 'underline' }}>
                Already have an account? Login
              </button>
            </div>
          </>
        ) : (
          <>
            <div style={{ fontSize: '4rem', marginBottom: '16px' }}>🚀</div>
            <h2 style={{ marginBottom: '8px', color: '#10b981' }}>You're All Set!</h2>
            <p style={{ color: 'var(--color-text-light)', marginBottom: '8px' }}>
              Your <strong>{planInfo?.name}</strong> plan is now active with{' '}
              <strong>{planInfo?.chases} chases/month</strong>.
            </p>
            <p style={{ color: 'var(--color-text-light)', marginBottom: '24px' }}>
              Time to stop chasing and let us do the work.
            </p>
            <button
              onClick={onGoToLogin}
              style={{
                width: '100%',
                padding: '14px',
                borderRadius: '8px',
                border: 'none',
                background: '#10b981',
                color: '#fff',
                fontSize: '1.1rem',
                fontWeight: 700,
                cursor: 'pointer'
              }}
            >
              Go to Dashboard →
            </button>
          </>
        )}
      </div>
    </div>
  );
};
