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

  useEffect(() => {
    // Read plan from URL params: /payment-success?plan=growth&session_id=...
    const params = new URLSearchParams(window.location.search);
    const planParam = params.get('plan');
    if (planParam && PLAN_DETAILS[planParam]) {
      setPlan(planParam);
    }
  }, []);

  const planInfo = plan ? PLAN_DETAILS[plan] : null;

  // Activation happens server-side via the Stripe webhook once payment is
  // confirmed — this page never calls an activation endpoint directly, since
  // trusting a client-supplied plan/email pair would let anyone grant
  // themselves a paid plan for free.
  return (
    <div className="login-page" style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div className="login-card" style={{ maxWidth: '500px', textAlign: 'center' }}>
        <div style={{ fontSize: '4rem', marginBottom: '16px' }}>🎉</div>
        <h2 style={{ marginBottom: '8px' }}>Payment Successful!</h2>

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

        <p style={{ color: 'var(--color-text-light)', marginBottom: '24px' }}>
          Your subscription is being activated — this usually takes just a few
          seconds. Register or log in below to get started; your plan will
          already be active on your account.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          <button
            onClick={onGoToRegister}
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
            }}
          >
            Create Your Account
          </button>
          <button
            onClick={onGoToLogin}
            style={{ background: 'none', border: 'none', color: 'var(--color-primary)', cursor: 'pointer', textDecoration: 'underline' }}
          >
            Already have an account? Log in
          </button>
        </div>
      </div>
    </div>
  );
};
