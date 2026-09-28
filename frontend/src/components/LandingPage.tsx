import { useEffect, useState } from 'react';
import './LandingPage.css';

async function startCheckout(plan: string, email: string): Promise<{ ok: true } | { ok: false; error: string }> {
  try {
    const res = await fetch('/api/payments/create-checkout-session', {
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
    // On success, startCheckout redirects the page — no further state needed.
  };

  return (
    <div className="checkout-modal-overlay" onClick={onClose}>
      <div className="checkout-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Get the {planName} plan</h3>
        <p>Enter your email to continue to secure checkout.</p>
        {error && <div className="checkout-modal-error">{error}</div>}
        <input
          type="email"
          placeholder="you@company.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && handleSubmit()}
          autoFocus
        />
        <button className="btn-gold" onClick={handleSubmit} disabled={!email || loading}>
          {loading ? 'Redirecting…' : 'Continue to Checkout'}
        </button>
        <button className="checkout-modal-close" onClick={onClose}>Cancel</button>
      </div>
    </div>
  );
};

export const LandingPage = ({ onGetStarted, onSignIn }: { onGetStarted: () => void, onSignIn: () => void }) => {
  const [activeTab, setActiveTab] = useState(0);
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
      // Anything already on/above screen on mount reveals immediately instead
      // of waiting for an intersection that has already happened.
      const rect = el.getBoundingClientRect();
      if (rect.top < window.innerHeight) {
        el.classList.add('active');
      } else {
        observer.observe(el);
      }
    });

    // Safety net: a fast scroll (trackpad flick, Page Down, jump-to-anchor)
    // can carry an element from below the viewport to above it between two
    // animation frames, so it's never "intersecting" and the observer misses
    // it. Reveal anything that is visible OR has been scrolled past entirely.
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

    return () => {
      observer.disconnect();
      window.removeEventListener('scroll', revealPassed);
    };
  }, []);

  const features = [
    {
      title: "Relentless Automation",
      description: "Set your custom escalation schedules once. Our system relentlessly tracks due dates, sends beautiful reminders, and escalates past-due accounts automatically without you lifting a finger.",
      image: "/feature-1.jpg"
    },
    {
      title: "White-Labeled Authority",
      description: "Perception is everything. We generate immaculate PDF invoices automatically branded with your logo, reinforcing your brand's authority and prestige with every touchpoint.",
      image: "/feature-2.jpg"
    },
    {
      title: "Bespoke Delivery",
      description: "Don't look like an automated system. Connect your own email server securely. Reminders come directly from your billing address, maintaining the illusion of personal, high-end follow-up.",
      image: "/feature-3.jpg"
    }
  ];

  return (
    <div className="landing-container">
      {/* Navigation */}
      <nav className="landing-nav animate-up-1">
        <div className="landing-brand">
          <h1>YourInbox<span>Hero</span></h1>
        </div>
        <div className="landing-nav-links">
          <button className="btn-nav-login" onClick={onSignIn}>SIGN IN</button>
          <button className="btn-gold" onClick={onGetStarted}>GET ACCESS</button>
        </div>
      </nav>

      {/* Hero Section */}
      <header className="hero-section">
        <div className="hero-content">
          <h1 className="hero-title animate-up-1">
            Stop asking again and again.<br/>
            <span>Let us get this for you.</span>
          </h1>
          <p className="hero-subtitle animate-up-2">
            Your time is too valuable to spend chasing unpaid invoices and documents. YourInboxHero is the elite, automated receivables engine built for high-performing businesses.
          </p>
          <div className="hero-cta animate-up-3">
            <button className="btn-gold-large" onClick={onGetStarted}>Start Automating Now</button>
            <span className="hero-cta-note">No Credit Card Required</span>
          </div>
        </div>
      </header>

      {/* Social Proof */}
      <section className="social-proof reveal">
        <p>Trusted by Elite Firms Worldwide</p>
        <div className="logo-grid">
          <div className="logo-item">Aura.</div>
          <div className="logo-item">Vanguard Partners</div>
          <div className="logo-item">LUMINA</div>
          <div className="logo-item">Apex Capital</div>
        </div>
      </section>

      {/* Problem Statement */}
      <section className="problem-statement reveal">
        <h2>You didn't start a business to become a <span>debt collector.</span></h2>
        <p>Every hour you spend tracking down unpaid invoices is an hour stolen from your growth. Reclaim your time, protect your cash flow, and maintain perfect client relationships by letting our system handle the uncomfortable follow-ups.</p>
      </section>

      {/* Interactive Feature Showcase */}
      <section className="showcase-section reveal">
        <div className="showcase-container">
          <div className="showcase-tabs">
            {features.map((feature, index) => (
              <div 
                key={index} 
                className={`showcase-tab ${activeTab === index ? 'active' : ''}`}
                onClick={() => setActiveTab(index)}
              >
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
              </div>
            ))}
          </div>
          <div className="showcase-visual">
            {features.map((feature, index) => (
              <img 
                key={index}
                src={feature.image}
                alt={feature.title}
                className="showcase-image"
                style={{ 
                  position: 'absolute', 
                  top: 0, left: 0, 
                  opacity: activeTab === index ? 1 : 0,
                  visibility: activeTab === index ? 'visible' : 'hidden'
                }}
              />
            ))}
          </div>
        </div>
      </section>

      {/* ROI Section */}
      <section className="roi-section reveal">
        <h2>The Compound Effect of Automation</h2>
        <div className="roi-grid">
          <div className="roi-stat">
            <div className="roi-number">14</div>
            <p>Days reduction in DSO</p>
          </div>
          <div className="roi-stat">
            <div className="roi-number">92%</div>
            <p>On-time payment rate</p>
          </div>
          <div className="roi-stat">
            <div className="roi-number">30+</div>
            <p>Hours saved per month</p>
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section className="pricing-section reveal">
        <h2 className="section-title">Choose Your Plan</h2>
        <div className="pricing-grid">
          
          <div className="pricing-card">
            <h3>Starter</h3>
            <div className="price">$149<span>/mo</span></div>
            <p style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', marginBottom: '16px' }}>100 chases — $1.49 per chase</p>
            <ul className="pricing-features">
              <li>100 automated chases/month</li>
              <li>Email + SMS reminders</li>
              <li>PDF invoice generation</li>
              <li>Payment link integration</li>
              <li>Document collection</li>
            </ul>
            <button onClick={() => setCheckoutPlan({ id: 'starter', name: 'Starter' })} className="btn-pricing">Get Starter</button>
          </div>

          <div className="pricing-card premium">
            <div className="premium-badge">The best deal</div>
            <h3 style={{ color: '#D4AF37' }}>Growth</h3>
            <div className="price" style={{ color: '#D4AF37' }}>$299<span>/mo</span></div>
            <p style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', marginBottom: '16px' }}>300 chases — $0.99 per chase</p>
            <ul className="pricing-features">
              <li>300 automated chases/month</li>
              <li>Email + SMS + Voice escalation</li>
              <li>Custom email templates</li>
              <li>White-labeled PDF logos</li>
              <li>Custom SMTP integration</li>
              <li>Priority support</li>
            </ul>
            <button onClick={() => setCheckoutPlan({ id: 'growth', name: 'Growth' })} className="btn-pricing">Get Growth</button>
          </div>

          <div className="pricing-card">
            <h3>Scale</h3>
            <div className="price">$497<span>/mo</span></div>
            <p style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', marginBottom: '16px' }}>750 chases — $0.66 per chase</p>
            <ul className="pricing-features">
              <li>750 automated chases/month</li>
              <li>Full 3-tier escalation engine</li>
              <li>Unlimited document requests</li>
              <li>Full API access</li>
              <li>Dedicated account manager</li>
              <li>Custom SLAs</li>
            </ul>
            <button onClick={() => setCheckoutPlan({ id: 'scale', name: 'Scale' })} className="btn-pricing">Get Scale</button>
          </div>

        </div>
      </section>
      
      {/* Footer */}
      <footer className="landing-footer">
        <p>&copy; {new Date().getFullYear()} YourInboxHero. Engineered for excellence.</p>
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
