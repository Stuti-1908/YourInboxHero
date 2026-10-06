import { useState, useEffect } from 'react';
import { Routes, Route, Navigate, useNavigate, useLocation } from 'react-router-dom';
import { InvoiceTable } from './components/InvoiceTable';
import { DebtorTable } from './components/DebtorTable';
import { Login } from './components/Login';
import { Register } from './components/Register';
import { Settings } from './components/Settings';
import { LandingPage } from './components/LandingPage';
import { CreateDebtor } from './components/CreateDebtor';
import { CreateInvoice } from './components/CreateInvoice';
import { ImportInvoices } from './components/ImportInvoices';
import Templates from './components/EmailTemplates';
import { EmailProviders } from './components/EmailProviders';
import { DocumentTable } from './components/DocumentTable';
import { CreateDocumentRequest } from './components/CreateDocumentRequest';
import { CreateDocumentClient } from './components/CreateDocumentClient';
import { PaymentSuccess } from './components/PaymentSuccess';
import { PublicDocumentUpload } from './components/PublicDocumentUpload';
import { VerifyEmail } from './components/VerifyEmail';
import { logout, getCompanyName } from './api/invoice';
import { AnalyticsDashboard } from './components/AnalyticsDashboard';
import './App.css';

const isLoggedIn = () => !!localStorage.getItem('token');

// Dashboard chrome (module switcher + nav tabs) shared by every authenticated
// route, with each tab as a real URL under /dashboard or /documents instead
// of in-memory state, so the back/forward buttons and bookmarks work.
const DashboardLayout = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const companyName = getCompanyName();

  const activeModule = location.pathname.startsWith('/documents') ? 'documents' : 'money';
  const isMoneyTab = (tab: string) => location.pathname === `/dashboard/${tab}`;
  const isDocTab = (tab: string) => location.pathname === `/documents/${tab}` || (tab === 'list' && location.pathname === '/documents');

  return (
    <div className="app-container fade-in">
      <div style={{
        display: 'flex',
        justifyContent: 'center',
        gap: '0',
        background: 'var(--color-bg-alt)',
        borderBottom: '1px solid var(--color-border)',
        padding: '0'
      }}>
        <button
          onClick={() => navigate('/dashboard')}
          style={{
            padding: '12px 32px',
            border: 'none',
            borderBottom: activeModule === 'money' ? '3px solid var(--color-primary)' : '3px solid transparent',
            background: 'transparent',
            fontWeight: activeModule === 'money' ? 700 : 400,
            fontSize: '0.95rem',
            cursor: 'pointer',
            color: activeModule === 'money' ? 'var(--color-primary)' : 'var(--color-text-light)'
          }}
        >
          Money Collection
        </button>
        <button
          onClick={() => navigate('/documents')}
          style={{
            padding: '12px 32px',
            border: 'none',
            borderBottom: activeModule === 'documents' ? '3px solid var(--color-primary)' : '3px solid transparent',
            background: 'transparent',
            fontWeight: activeModule === 'documents' ? 700 : 400,
            fontSize: '0.95rem',
            cursor: 'pointer',
            color: activeModule === 'documents' ? 'var(--color-primary)' : 'var(--color-text-light)'
          }}
        >
          Document Collection
        </button>
      </div>

      <header className="top-nav">
        <div className="nav-brand">
          <h1>{companyName === 'YourInboxHero' ? <>YourInbox<span>Hero</span></> : <span>{companyName}</span>}</h1>
        </div>
        <div className="nav-controls">
          {activeModule === 'money' ? (
            <>
              <button className={`nav-tab ${isMoneyTab('analytics') ? 'active' : ''}`} onClick={() => navigate('/dashboard/analytics')}>Analytics</button>
              <button className={`nav-tab ${isMoneyTab('invoices') ? 'active' : ''}`} onClick={() => navigate('/dashboard/invoices')}>Invoices</button>
              <button className={`nav-tab ${isMoneyTab('debtors') ? 'active' : ''}`} onClick={() => navigate('/dashboard/debtors')}>Debtors</button>
              <button className={`nav-tab ${isMoneyTab('debtors/new') ? 'active' : ''}`} onClick={() => navigate('/dashboard/debtors/new')}>Add Debtor</button>
              <button className={`nav-tab ${isMoneyTab('invoices/new') ? 'active' : ''}`} onClick={() => navigate('/dashboard/invoices/new')}>Add Invoice</button>
              <button className={`nav-tab ${isMoneyTab('invoices/import') ? 'active' : ''}`} onClick={() => navigate('/dashboard/invoices/import')}>Import CSV</button>
              <button className={`nav-tab ${isMoneyTab('templates') ? 'active' : ''}`} onClick={() => navigate('/dashboard/templates')}>Templates</button>
              <button className={`nav-tab ${isMoneyTab('email-setup') ? 'active' : ''}`} onClick={() => navigate('/dashboard/email-setup')}>Email Setup</button>
              <button className={`nav-tab ${isMoneyTab('settings') ? 'active' : ''}`} onClick={() => navigate('/dashboard/settings')}>Settings</button>
            </>
          ) : (
            <>
              <button className={`nav-tab ${isDocTab('list') ? 'active' : ''}`} onClick={() => navigate('/documents')}>Documents</button>
              <button className={`nav-tab ${isDocTab('new') ? 'active' : ''}`} onClick={() => navigate('/documents/new')}>Request Document</button>
              <button className={`nav-tab ${isDocTab('clients/new') ? 'active' : ''}`} onClick={() => navigate('/documents/clients/new')}>Add Client</button>
              <button className="nav-tab" onClick={() => navigate('/dashboard/settings')}>Settings</button>
            </>
          )}
          <button className="nav-logout" onClick={() => { logout(); navigate('/'); }}>Sign Out</button>
        </div>
      </header>

      <main className="main-content">
        <div className="fade-in" key={location.pathname}>
          <Routes>
            <Route path="/dashboard" element={<Navigate to="/dashboard/analytics" replace />} />
            <Route path="/dashboard/analytics" element={<AnalyticsDashboard />} />
            <Route path="/dashboard/invoices" element={<InvoiceTable />} />
            <Route path="/dashboard/debtors" element={<DebtorTable />} />
            <Route path="/dashboard/debtors/new" element={<CreateDebtor onSuccess={() => navigate('/dashboard/debtors')} />} />
            <Route path="/dashboard/invoices/new" element={<CreateInvoice onSuccess={() => navigate('/dashboard/invoices')} />} />
            <Route path="/dashboard/invoices/import" element={<ImportInvoices onSuccess={() => navigate('/dashboard/invoices')} />} />
            <Route path="/dashboard/templates" element={<Templates />} />
            <Route path="/dashboard/email-setup" element={<EmailProviders />} />
            <Route path="/dashboard/settings" element={<Settings />} />
            <Route path="/documents" element={<DocumentTable />} />
            <Route path="/documents/new" element={<CreateDocumentRequest onSuccess={() => navigate('/documents')} />} />
            <Route path="/documents/clients/new" element={<CreateDocumentClient onSuccess={() => navigate('/documents/new')} />} />
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
  );
}

export default App;
