import React from 'react';
import { InvoiceTable } from './components/InvoiceTable';
import './App.css';

function App() {
  return (
    <div>
      <header style={{ padding: '10px 20px', backgroundColor: '#1e293b', color: 'white' }}>
        <h1>YourInboxHero Dashboard</h1>
      </header>
      <main>
        <InvoiceTable />
      </main>
    </div>
  );
}

export default App;
