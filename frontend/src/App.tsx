import { useState, useEffect } from 'react';
import { InvoiceTable } from './components/InvoiceTable';
import { DebtorTable } from './components/DebtorTable';
import { Login } from './components/Login';
import { Register } from './components/Register';
import { Settings } from './components/Settings';
import { LandingPage } from './components/LandingPage';
import { CreateDebtor } from './components/CreateDebtor';
import { CreateInvoice } from './components/CreateInvoice';
import Templates from './components/EmailTemplates';
import { EmailProviders } from './components/EmailProviders';
import { DocumentTable } from './components/DocumentTable';
import { CreateDocumentRequest } from './components/CreateDocumentRequest';
import { CreateDocumentClient } from './components/CreateDocumentClient';
import { PaymentSuccess } from './components/PaymentSuccess';
import { logout, getCompanyName } from './api/invoice';
import { AnalyticsDashboard } from './components/AnalyticsDashboard';
import './App.css';

type Module = 'money' | 'documents';
type MoneyTab = 'analytics' | 'dashboard' | 'debtors' | 'addDebtor' | 'addInvoice' | 'templates' | 'emailProviders' | 'settings';
type DocTab = 'docList' | 'addDoc' | 'addClient';
type PublicPage = 'landing' | 'login' | 'register' | 'payment-success';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [publicPage, setPublicPage] = useState<PublicPage>('landing');
  const [activeModule, setActiveModule] = useState<Module>('money');
  const [moneyTab, setMoneyTab] = useState<MoneyTab>('analytics');
  const [docTab, setDocTab] = useState<DocTab>('docList');

  useEffect(() => {
    setIsAuthenticated(!!localStorage.getItem('token'));
    
    // Check if user is returning from Square checkout
    const params = new URLSearchParams(window.location.search);
    if (params.get('plan')) {
      setPublicPage('payment-success');
    }
  }, []);

  const companyName = getCompanyName();

  return (
    <div className="app-container fade-in">
      {isAuthenticated && (
        <>
          {/* Module Switcher Bar */}
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            gap: '0',
            background: 'var(--color-bg-alt)',
            borderBottom: '1px solid var(--color-border)',
            padding: '0'
          }}>
            <button
              onClick={() => setActiveModule('money')}
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
              💰 Money Collection
            </button>
            <button
              onClick={() => setActiveModule('documents')}
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
              📄 Document Collection
            </button>
          </div>

          {/* Navigation Bar */}
          <header className="top-nav">
            <div className="nav-brand">
              <h1>{companyName === 'YourInboxHero' ? <>YourInbox<span>Hero</span></> : <span>{companyName}</span>}</h1>
            </div>
            <div className="nav-controls">
              {activeModule === 'money' ? (
                <>
                  <button className={`nav-tab ${moneyTab === 'analytics' ? 'active' : ''}`} onClick={() => setMoneyTab('analytics')}>Analytics</button>
                  <button className={`nav-tab ${moneyTab === 'dashboard' ? 'active' : ''}`} onClick={() => setMoneyTab('dashboard')}>Invoices</button>
                  <button className={`nav-tab ${moneyTab === 'debtors' ? 'active' : ''}`} onClick={() => setMoneyTab('debtors')}>Debtors</button>
                  <button className={`nav-tab ${moneyTab === 'addDebtor' ? 'active' : ''}`} onClick={() => setMoneyTab('addDebtor')}>Add Debtor</button>
                  <button className={`nav-tab ${moneyTab === 'addInvoice' ? 'active' : ''}`} onClick={() => setMoneyTab('addInvoice')}>Add Invoice</button>
                  <button className={`nav-tab ${moneyTab === 'templates' ? 'active' : ''}`} onClick={() => setMoneyTab('templates')}>Templates</button>
                  <button className={`nav-tab ${moneyTab === 'emailProviders' ? 'active' : ''}`} onClick={() => setMoneyTab('emailProviders')}>Email Setup</button>
                  <button className={`nav-tab ${moneyTab === 'settings' ? 'active' : ''}`} onClick={() => setMoneyTab('settings')}>Settings</button>
                </>
              ) : (
                <>
                  <button className={`nav-tab ${docTab === 'docList' ? 'active' : ''}`} onClick={() => setDocTab('docList')}>Documents</button>
                  <button className={`nav-tab ${docTab === 'addDoc' ? 'active' : ''}`} onClick={() => setDocTab('addDoc')}>Request Document</button>
                  <button className={`nav-tab ${docTab === 'addClient' ? 'active' : ''}`} onClick={() => setDocTab('addClient')}>Add Client</button>
                  <button className={`nav-tab ${moneyTab === 'settings' ? 'active' : ''}`} onClick={() => { setActiveModule('money'); setMoneyTab('settings'); }}>Settings</button>
                </>
              )}
              <button className="nav-logout" onClick={logout}>Sign Out</button>
            </div>
          </header>
        </>
      )}

      {isAuthenticated ? (
        <main className="main-content">
          {activeModule === 'money' ? (
            <div className="fade-in" key={moneyTab}>
              {moneyTab === 'analytics' && <AnalyticsDashboard />}
              {moneyTab === 'dashboard' && <InvoiceTable />}
              {moneyTab === 'debtors' && <DebtorTable />}
              {moneyTab === 'addDebtor' && <CreateDebtor onSuccess={() => setMoneyTab('debtors')} />}
              {moneyTab === 'addInvoice' && <CreateInvoice onSuccess={() => setMoneyTab('dashboard')} />}
              {moneyTab === 'templates' && <Templates />}
              {moneyTab === 'emailProviders' && <EmailProviders />}
              {moneyTab === 'settings' && <Settings />}
            </div>
          ) : (
            <div className="fade-in" key={docTab}>
              {docTab === 'docList' && <DocumentTable />}
              {docTab === 'addDoc' && <CreateDocumentRequest onSuccess={() => setDocTab('docList')} />}
              {docTab === 'addClient' && <CreateDocumentClient onSuccess={() => setDocTab('addDoc')} />}
            </div>
          )}
        </main>
      ) : publicPage === 'payment-success' ? (
        <PaymentSuccess
          onGoToRegister={() => setPublicPage('register')}
          onGoToLogin={() => setPublicPage('login')}
        />
      ) : publicPage === 'landing' ? (
        <LandingPage onGetStarted={() => setPublicPage('register')} onSignIn={() => setPublicPage('login')} />
      ) : publicPage === 'register' ? (
        <Register onRegisterSuccess={() => setIsAuthenticated(true)} onSwitchToLogin={() => setPublicPage('login')} />
      ) : (
        <Login onLoginSuccess={() => setIsAuthenticated(true)} onSwitchToRegister={() => setPublicPage('register')} />
      )}
    </div>
  );
}

export default App;
