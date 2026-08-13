import React, { useState, useEffect } from 'react';
import { InvoiceTable } from './components/InvoiceTable';
import { DebtorTable } from './components/DebtorTable';
import { Login } from './components/Login';
import { CreateDebtor } from './components/CreateDebtor';
import { CreateInvoice } from './components/CreateInvoice';
import { logout } from './api/invoice';
import './App.css';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'debtors' | 'addDebtor' | 'addInvoice'>('dashboard');

  useEffect(() => {
    setIsAuthenticated(!!localStorage.getItem('token'));
  }, []);

  const handleTabChange = (tab: 'dashboard' | 'debtors' | 'addDebtor' | 'addInvoice') => {
    setActiveTab(tab);
  };

  return (
    <div className="app-container fade-in">
      {isAuthenticated && (
        <header className="top-nav">
          <div className="nav-brand">
            <h1>YourInbox<span>Hero</span></h1>
          </div>
          <div className="nav-controls">
            <button 
              className={`nav-tab ${activeTab === 'dashboard' ? 'active' : ''}`}
              onClick={() => handleTabChange('dashboard')}
            >
              Invoices
            </button>
            <button 
              className={`nav-tab ${activeTab === 'debtors' ? 'active' : ''}`}
              onClick={() => handleTabChange('debtors')}
            >
              Debtors
            </button>
            <button 
              className={`nav-tab ${activeTab === 'addDebtor' ? 'active' : ''}`}
              onClick={() => handleTabChange('addDebtor')}
            >
              Add Debtor
            </button>
            <button 
              className={`nav-tab ${activeTab === 'addInvoice' ? 'active' : ''}`}
              onClick={() => handleTabChange('addInvoice')}
            >
              Add Invoice
            </button>
            <button className="nav-logout" onClick={logout}>
              Sign Out
            </button>
          </div>
        </header>
      )}
      <main className="main-content">
        {isAuthenticated ? (
          <div className="fade-in" key={activeTab}>
            {activeTab === 'dashboard' && <InvoiceTable />}
            {activeTab === 'debtors' && <DebtorTable />}
            {activeTab === 'addDebtor' && <CreateDebtor onSuccess={() => handleTabChange('debtors')} />}
            {activeTab === 'addInvoice' && <CreateInvoice onSuccess={() => handleTabChange('dashboard')} />}
          </div>
        ) : (
          <Login onLoginSuccess={() => setIsAuthenticated(true)} />
        )}
      </main>
    </div>
  );
}

export default App;
