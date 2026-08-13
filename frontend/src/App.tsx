import React, { useState, useEffect } from 'react';
import { InvoiceTable } from './components/InvoiceTable';
import { Login } from './components/Login';
import { logout } from './api/invoice';
import './App.css';

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    setIsAuthenticated(!!localStorage.getItem('token'));
  }, []);

  return (
    <div>
      <header style={{ padding: '10px 20px', backgroundColor: '#1e293b', color: 'white', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h1 style={{ margin: 0 }}>YourInboxHero Dashboard</h1>
        {isAuthenticated && (
          <button 
            onClick={logout} 
            style={{ padding: '6px 12px', cursor: 'pointer', backgroundColor: '#ef4444', color: 'white', border: 'none', borderRadius: '4px' }}
          >
            Logout
          </button>
        )}
      </header>
      <main>
        {isAuthenticated ? (
          <InvoiceTable />
        ) : (
          <Login onLoginSuccess={() => setIsAuthenticated(true)} />
        )}
      </main>
    </div>
  );
}

export default App;
