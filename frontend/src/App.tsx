import { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { Login } from './components/Login';
import { Register } from './components/Register';
import { Settings } from './components/Settings';
import { LandingPage } from './components/LandingPage';
import { InvoicesPage } from './components/InvoicesPage';
import { DebtorsPage } from './components/DebtorsPage';
import { DocumentsPage } from './components/DocumentsPage';
import { PaymentSuccess } from './components/PaymentSuccess';
import { PublicDocumentUpload } from './components/PublicDocumentUpload';
import { VerifyEmail } from './components/VerifyEmail';
import { logout, getCompanyName, refreshToken } from './api/invoice';
import { ErrorBoundary } from './components/ErrorBoundary';
import { AnalyticsDashboard } from './components/AnalyticsDashboard';
import { ReminderHistory } from './components/ReminderHistory';
import './App.css';

const isLoggedIn = () => !!localStorage.getItem('token');

const MONEY_TABS = [
  { path: '/dashboard/analytics', label: 'Analytics' },
  { path: '/dashboard/invoices', label: 'Invoices' },
  { path: '/dashboard/debtors', label: 'Debtors' },
  { path: '/dashboard/history', label: 'History' },
  { path: '/dashboard/settings', label: 'Settings' },
];

const DOC_TABS = [
  { path: '/documents', label: 'Documents' },
  { path: '/documents/settings', label: 'Settings' },
];

// Dashboard chrome (module switcher + nav tabs) shared by every authenticated
// route, with each tab as a real URL under /dashboard or /documents instead
// of in-memory state, so the back/forward buttons and bookmarks work.
const DashboardLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const companyName = getCompanyName();
  const [menuOpen, setMenuOpen] = useState(false);

  // Silently slide the 30-minute token expiry forward every 10 minutes
  // while the dashboard is open, so an actively-working user isn't logged
  // out mid-session. If the token has already expired, refreshToken()
  // fails harmlessly and the next real API call's 401 handling takes over.
  useEffect(() => {
    const interval = setInterval(() => {
      refreshToken();
    }, 10 * 60 * 1000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname]);

  const activeModule = location.pathname.startsWith('/documents') ? 'documents' : 'money';
  const tabs = activeModule === 'money' ? MONEY_TABS : DOC_TABS;

  return (
    <div className="app-container fade-in">
      <div className="module-switch">
        <button className={activeModule === 'money' ? 'active' : ''} onClick={() => navigate('/dashboard')}>
          Money Collection
        </button>
        <button className={activeModule === 'documents' ? 'active' : ''} onClick={() => navigate('/documents')}>
          Document Collection
        </button>
      </div>

      <header className="top-nav">
        <div className="nav-brand">
          <h1>{companyName === 'YourInboxHero' ? <>YourInbox<span>Hero</span></> : <span>{companyName}</span>}</h1>
        </div>
        <button
          className="nav-toggle"
          aria-expanded={menuOpen}
          aria-label="Toggle navigation menu"
          onClick={() => setMenuOpen(o => !o)}
        >
          {menuOpen ? 'Close' : 'Menu'}
        </button>
        <nav className={`nav-controls ${menuOpen ? 'open' : ''}`}>
          {tabs.map(t => (
            <button
              key={t.path}
              className={`nav-tab ${location.pathname === t.path ? 'active' : ''}`}
              onClick={() => navigate(t.path)}
            >
              {t.label}
            </button>
          ))}
          <button className="nav-logout" onClick={() => { logout().finally(() => navigate('/')); }}>Sign Out</button>
        </nav>
      </header>

      <main className="main-content">
        <div className="fade-in" key={location.pathname}>
          <Routes>
            <Route path="/dashboard" element={<Navigate to="/dashboard/analytics" replace />} />
            <Route path="/dashboard/analytics" element={<AnalyticsDashboard />} />
            <Route path="/dashboard/invoices" element={<InvoicesPage />} />
            <Route path="/dashboard/debtors" element={<DebtorsPage />} />
            <Route path="/dashboard/history" element={<ReminderHistory />} />
            <Route path="/dashboard/settings" element={<Settings />} />
            <Route path="/documents" element={<DocumentsPage />} />
            <Route path="/documents/settings" element={<Settings />} />

            {/* Old URLs (bookmarks, emails, earlier builds) */}
            <Route path="/dashboard/debtors/new" element={<Navigate to="/dashboard/debtors?new=1" replace />} />
            <Route path="/dashboard/invoices/new" element={<Navigate to="/dashboard/invoices?new=1" replace />} />
            <Route path="/dashboard/invoices/import" element={<Navigate to="/dashboard/invoices?import=1" replace />} />
            <Route path="/dashboard/templates" element={<Navigate to="/dashboard/settings#templates" replace />} />
            <Route path="/dashboard/email-setup" element={<Navigate to="/dashboard/settings#email" replace />} />
            <Route path="/documents/new" element={<Navigate to="/documents?new=1" replace />} />
            <Route path="/documents/clients/new" element={<Navigate to="/documents?new=1" replace />} />

            <Route path="*" element={<Navigate to="/dashboard/analytics" replace />} />
          </Routes>
        </div>
      </main>
    </div>
  );
};

function App() {
  const [authed, setAuthed] = useState(isLoggedIn());
  const navigate = useNavigate();

  useEffect(() => {
    setAuthed(isLoggedIn());
  }, []);

  const handleLoginSuccess = () => {
    setAuthed(true);
    navigate('/dashboard');
  };

  // The document-upload and email-verification links are public and must
  // work regardless of whether the viewing device happens to have a login
  // token — e.g. a business owner opening their own upload link to test
  // it, or clicking a verification link on a device they're already
  // logged in on. Hoisted above the authed/unauthed branches below so
  // neither can shadow them.
  return (
    <ErrorBoundary>
      <Routes>
        <Route path="/upload/:token" element={<PublicDocumentUpload />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route
          path="/*"
          element={
            authed ? (
              <DashboardLayout />
            ) : (
              <Routes>
                <Route path="/" element={<LandingPage onGetStarted={() => navigate('/sign-up')} onSignIn={() => navigate('/sign-in')} />} />
                <Route path="/sign-in" element={<Login onLoginSuccess={handleLoginSuccess} onSwitchToRegister={() => navigate('/sign-up')} />} />
                <Route path="/sign-up" element={<Register onSwitchToLogin={() => navigate('/sign-in')} onViewPricing={() => navigate('/#pricing')} />} />
                <Route path="/payment-success" element={<PaymentSuccess onGoToRegister={() => navigate('/sign-up')} onGoToLogin={() => navigate('/sign-in')} />} />
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            )
          }
        />
      </Routes>
    </ErrorBoundary>
  );
}

export default App;
