import React, { useState, useEffect } from 'react';
import { InvoiceTable } from './components/InvoiceTable';
import { Login } from './components/Login';
import { CreateDebtor } from './components/CreateDebtor';
import { CreateInvoice } from './components/CreateInvoice';
import { logout } from './api/invoice';
import './App.css';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'addDebtor' | 'addInvoice'>('dashboard');

  useEffect(() => {
    setIsAuthenticated(!!localStorage.getItem('token'));
  }, []);

  const handleTabChange = (tab: 'dashboard' | 'addDebtor' | 'addInvoice') => {
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
              Dashboard
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
            {activeTab === 'addDebtor' && <CreateDebtor onSuccess={() => handleTabChange('dashboard')} />}
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
