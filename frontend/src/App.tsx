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
    <div>
      <header style={{ padding: '10px 20px', backgroundColor: '#1e293b', color: 'white', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 style={{ margin: 0 }}>YourInboxHero Dashboard</h1>
        {isAuthenticated && (
          <div>
            <button onClick={() => handleTabChange('dashboard')} style={{ marginRight: '10px', background: activeTab === 'dashboard' ? '#3b82f6' : 'transparent', color: 'white', border: '1px solid #3b82f6', borderRadius: '4px', padding: '6px 12px', cursor: 'pointer' }}>Dashboard</button>
            <button onClick={() => handleTabChange('addDebtor')} style={{ marginRight: '10px', background: activeTab === 'addDebtor' ? '#3b82f6' : 'transparent', color: 'white', border: '1px solid #3b82f6', borderRadius: '4px', padding: '6px 12px', cursor: 'pointer' }}>Add Debtor</button>
            <button onClick={() => handleTabChange('addInvoice')} style={{ marginRight: '10px', background: activeTab === 'addInvoice' ? '#3b82f6' : 'transparent', color: 'white', border: '1px solid #3b82f6', borderRadius: '4px', padding: '6px 12px', cursor: 'pointer' }}>Add Invoice</button>
            <button 
              onClick={logout} 
              style={{ padding: '6px 12px', cursor: 'pointer', backgroundColor: '#ef4444', color: 'white', border: 'none', borderRadius: '4px' }}
            >
              Logout
            </button>
          </div>
        )}
      </header>
      <main style={{ padding: '20px', maxWidth: '1000px', margin: '0 auto' }}>
        {isAuthenticated ? (
          <>
            {activeTab === 'dashboard' && <InvoiceTable />}
            {activeTab === 'addDebtor' && <CreateDebtor onSuccess={() => handleTabChange('dashboard')} />}
            {activeTab === 'addInvoice' && <CreateInvoice onSuccess={() => handleTabChange('dashboard')} />}
          </>
        ) : (
          <Login onLoginSuccess={() => setIsAuthenticated(true)} />
        )}
      </main>
    </div>
  );
}

export default App;
