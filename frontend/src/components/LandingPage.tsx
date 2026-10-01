import { useEffect, useState } from 'react';
import { API_BASE } from '../api/invoice';
import './LandingPage.css';

async function startCheckout(plan: string, email: string): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const res = await fetch(`${API_BASE}/api/payments/create-checkout-session`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan, email }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      return { ok: false, error: data.detail || 'Could not start checkout. Please try again.' };
    }
    const data = await res.json();
    window.location.href = data.checkout_url;
    return { ok: true };
  } catch {
    return { ok: false, error: 'Connection error. Please try again.' };
  }
}

const PlanCheckoutModal = ({ plan, planName, onClose }: { plan: string; planName: string; onClose: () => void }) => {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    if (!email) return;
    setLoading(true);
    setError('');
    const result = await startCheckout(plan, email);
    if (!result.ok) {
      setError(result.error);
      setLoading(false);
    }
  };

  return (
    <div className="checkout-modal-overlay" onClick={onClose}>
      <div className="checkout-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Get the {planName} plan</h3>
        <p>Enter your email to continue to checkout.</p>
        {error && <div className="checkout-modal-error">{error}</div>}
        <input
          type="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          autoFocus
        />
        <button className="btn-primary" onClick={handleSubmit} disabled={!email || loading}>
          {loading ? 'Redirecting…' : 'Continue to checkout'}
        </button>
        <button className="checkout-modal-close" onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
};

// The hero's centerpiece: a real invoice moving through the states the
// product actually manages. Each stage holds briefly then advances — the
// one orchestrated motion moment on the page.
const TIMELINE_STAGES = [
  { label: 'Invoice sent', date: 'Mar 3', state: 'sent', detail: 'INV-0148 · $4,200 · Net 30' },
  { label: 'Reminder sent', date: 'Mar 28', state: 'reminder', detail: 'Due in 2 days — email sent automatically' },
  { label: 'Due date passed', date: 'Apr 2', state: 'due', detail: 'Escalation begins — SMS queued' },
  { label: 'Paid in full', date: 'Apr 4', state: 'paid', detail: '$4,200 received · invoice closed' },
];

const InvoiceTimeline = () => {
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setStage((s) => (s + 1) % TIMELINE_STAGES.length);
    }, 2600);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="timeline-card" aria-label="How an invoice moves through YourInboxHero">
      <div className="timeline-card-header">
        <span className="timeline-card-title">Acme Supply Co.</span>
        <span className={`timeline-status timeline-status-${TIMELINE_STAGES[stage].state}`}>
          {TIMELINE_STAGES[stage].state === 'paid' ? 'Paid' : TIMELINE_STAGES[stage].state === 'due' ? 'Overdue' : 'Upcoming'}
        </span>
      </div>
      <div className="timeline-track">
        {TIMELINE_STAGES.map((s, i) => (
          <div key={s.label} className={`timeline-step ${i <= stage ? 'is-reached' : ''} ${i === stage ? 'is-current' : ''}`}>
            <div className="timeline-dot" />
            <div className="timeline-step-body">
              <div className="timeline-step-top">
                <span className="timeline-step-label">{s.label}</span>
                <span className="timeline-step-date">{s.date}</span>
              </div>
              {i === stage && <p className="timeline-step-detail">{s.detail}</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export const LandingPage = ({ onGetStarted, onSignIn }: { onGetStarted: () => void, onSignIn: () => void }) => {
  const [checkoutPlan, setCheckoutPlan] = useState<{ id: string; name: string } | null>(null);

  useEffect(() => {
    const hiddenElements = document.querySelectorAll('.reveal');

    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add('active');
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.1, rootMargin: '0px 0px -10% 0px' });

    hiddenElements.forEach((el) => {
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight) {
        el.classList.add('active');
      } else {
        observer.observe(el);
      }
    });

    // Safety net #1: a fast scroll can carry a section past the viewport
    // between animation frames, so the observer never fires for it. Catch
    // anything left behind on scroll/resize and reveal it immediately.
    const revealPassed = () => {
      document.querySelectorAll('.reveal:not(.active)').forEach((el) => {
        const rect = el.getBoundingClientRect();
        if (rect.top < window.innerHeight) {
          el.classList.add('active');
          observer.unobserve(el);
        }
      });
    };
    window.addEventListener('scroll', revealPassed, { passive: true });
    window.addEventListener('resize', revealPassed);

    // Safety net #2: sections still below the fold on load are correctly
    // left hidden until scrolled to — that's the intended reveal effect,
    // not a bug. But if nothing ever gets the visitor to scroll far enough
    // (or scrolls that don't dispatch a `scroll` event slip past net #1),
    // a section can otherwise stay invisible forever with no way to
    // recover. After a few seconds with no further progress, force
    // everything visible rather than risk permanently hiding real content.
    let pollCount = 0;
    const pollInterval = window.setInterval(() => {
      pollCount += 1;
      revealPassed();
      const stillHidden = document.querySelectorAll('.reveal:not(.active)').length;
      if (stillHidden === 0) {
        window.clearInterval(pollInterval);
      } else if (pollCount > 8) {
        document.querySelectorAll('.reveal:not(.active)').forEach((el) => {
          el.classList.add('active');
          observer.unobserve(el);
        });
        window.clearInterval(pollInterval);
      }
    }, 250);

    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', revealPassed);
      window.removeEventListener('resize', revealPassed);
      window.clearInterval(pollInterval);
    };
  }, []);

  const steps = [
    {
      title: 'You send the invoice',
      body: 'Add the invoice once — amount, due date, payment link. YourInboxHero takes it from there.',
    },
    {
      title: 'We remind, before it\'s due',
      body: 'A branded email goes out a few days ahead of the due date. No automation kicks in after the invoice is overdue — that stays out of automated hands by design.',
    },
    {
      title: 'Overdue gets escalated, not ignored',
      body: 'If a client still hasn\'t paid, the reminder moves to a text message, and eventually a call from your team — never a robocall, never a stranger\'s name on the line.',
    },
    {
      title: 'You see everything, always',
      body: 'Every email, text, and call is logged against the invoice. Pause any client at any time. Nothing sends without your rules.',
    },
  ];

  const guardrails = [
    { title: 'Business invoices only', body: 'Built for B2B receivables — not personal debt collection, and never treated like it.' },
    { title: 'Never chases after the due date automatically', body: 'Pre-due reminders are automated. Anything past due moves through a tier your team controls, on a schedule you set.' },
    { title: 'Every send is logged', body: 'A full audit trail for every reminder — channel, timestamp, and content — attached to the invoice it belongs to.' },
  ];

  return (
    <div className="landing-container">
      <nav className="landing-nav">
        <div className="landing-brand">
          <span className="landing-brand-mark">YIH</span>
          <span className="landing-brand-name">YourInboxHero</span>
        </div>
        <div className="landing-nav-links">
          <button className="btn-nav-login" onClick={onSignIn}>Sign in</button>
          <button className="btn-primary btn-nav-cta" onClick={onGetStarted}>Get started</button>
        </div>
      </nav>

      <header className="hero-section">
        <div className="hero-grid">
          <div className="hero-content">
            <h1 className="hero-title">
              Unpaid invoices get followed up on.
              <br />Automatically. On schedule.
            </h1>
            <p className="hero-subtitle">
              YourInboxHero tracks every invoice you send and follows up before and after
              the due date — email, then text, then a call from your team — so you stop
              chasing payments by hand.
            </p>
            <div className="hero-cta">
              <button className="btn-primary btn-hero" onClick={onGetStarted}>Start automating</button>
              <span className="hero-cta-note">No credit card required</span>
            </div>
          </div>
          <div className="hero-visual">
            <InvoiceTimeline />
          </div>
        </div>
      </header>

      <section className="process-section reveal">
        <div className="section-heading">
          <h2>How a reminder actually moves</h2>
          <p>Four steps, the same order, every time.</p>
        </div>
        <div className="process-grid">
          {steps.map((step, i) => (
            <div className="process-step" key={step.title}>
              <span className="process-step-index">{String(i + 1).padStart(2, '0')}</span>
              <h3>{step.title}</h3>
              <p>{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="product-shots-section reveal">
        <div className="section-heading">
          <h2>See it in action</h2>
          <p>The actual dashboard — not a mockup. This is what you'll be working in from day one.</p>
        </div>
        <div className="product-shots-grid">
          <div className="product-shot">
            <div className="product-shot-frame">
              <div className="product-shot-chrome">
                <span /><span /><span />
              </div>
              <img src="/dashboard-invoices.png" alt="The invoices dashboard, showing invoice numbers, amounts, due dates, and overdue or upcoming status for each one" loading="lazy" />
            </div>
            <p className="product-shot-caption">Every invoice, its status, and one click to pause reminders or pull a PDF.</p>
          </div>
          <div className="product-shot">
            <div className="product-shot-frame">
              <div className="product-shot-chrome">
                <span /><span /><span />
              </div>
              <img src="/dashboard-analytics.png" alt="The analytics dashboard, showing total outstanding, total recovered, recovery rate, an aging report, and a status breakdown" loading="lazy" />
            </div>
            <p className="product-shot-caption">Outstanding balance, aging, and recovery — at a glance, updated as reminders go out.</p>
          </div>
        </div>
      </section>

      <section className="guardrails-section reveal">
        <div className="section-heading">
          <h2>Built with limits on purpose</h2>
          <p>The parts of receivables that shouldn't be left to automation, aren't.</p>
        </div>
        <div className="guardrails-grid">
          {guardrails.map((g) => (
            <div className="guardrail-card" key={g.title}>
              <h3>{g.title}</h3>
              <p>{g.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="pricing-section reveal">
        <div className="section-heading">
          <h2>Choose your plan</h2>
          <p>Priced by how many reminders you send a month, not by seat.</p>
        </div>
        <div className="pricing-grid">
          <div className="pricing-card">
            <div className="pricing-card-head">
              <h3>Starter</h3>
              <div className="price"><span className="price-amount">$149</span><span className="price-period">/mo</span></div>
              <p className="price-note">100 reminders · $1.49 each</p>
            </div>
            <ul className="pricing-features">
              <li>100 automated reminders a month</li>
              <li>Email + SMS escalation</li>
              <li>PDF invoice generation</li>
              <li>Payment link on every reminder</li>
              <li>Document collection included</li>
            </ul>
            <button onClick={() => setCheckoutPlan({ id: 'starter', name: 'Starter' })} className="btn-pricing">Get Starter</button>
          </div>

          <div className="pricing-card pricing-card-featured">
            <div className="pricing-card-badge">Most teams choose this</div>
            <div className="pricing-card-head">
              <h3>Growth</h3>
              <div className="price"><span className="price-amount">$299</span><span className="price-period">/mo</span></div>
              <p className="price-note">300 reminders · $0.99 each</p>
            </div>
            <ul className="pricing-features">
              <li>300 automated reminders a month</li>
              <li>Email + SMS + voice escalation</li>
              <li>Custom reminder templates</li>
              <li>Your logo on every invoice</li>
              <li>Send from your own domain</li>
              <li>Priority support</li>
            </ul>
            <button onClick={() => setCheckoutPlan({ id: 'growth', name: 'Growth' })} className="btn-pricing btn-pricing-featured">Get Growth</button>
          </div>

          <div className="pricing-card">
            <div className="pricing-card-head">
              <h3>Scale</h3>
              <div className="price"><span className="price-amount">$497</span><span className="price-period">/mo</span></div>
              <p className="price-note">750 reminders · $0.66 each</p>
            </div>
            <ul className="pricing-features">
              <li>750 automated reminders a month</li>
              <li>Full email, SMS, and voice ladder</li>
              <li>Unlimited document requests</li>
              <li>Full API access</li>
              <li>Dedicated account manager</li>
              <li>Custom SLAs</li>
            </ul>
            <button onClick={() => setCheckoutPlan({ id: 'scale', name: 'Scale' })} className="btn-pricing">Get Scale</button>
          </div>
        </div>
      </section>

      <footer className="landing-footer">
        <span>YourInboxHero</span>
        <span>&copy; {new Date().getFullYear()}</span>
      </footer>

      {checkoutPlan && (
        <PlanCheckoutModal
          plan={checkoutPlan.id}
          planName={checkoutPlan.name}
          onClose={() => setCheckoutPlan(null)}
        />
      )}
    </div>
  );
};
