import { useState, useEffect } from 'react';
import { getMe, updateSettings } from '../api/invoice';
import './Forms.css';

interface ProviderConfig {
  name: string;
  icon: string;
  host: string;
  port: string;
  instructions: string[];
}

const PROVIDERS: ProviderConfig[] = [
  {
    name: 'Google (Gmail)',
    icon: '📧',
    host: 'smtp.gmail.com',
    port: '587',
    instructions: [
      'Go to your Google Account → Security.',
      'Enable 2-Step Verification if not already on.',
      'Go to Security → App Passwords.',
      'Select "Mail" as the app and your device type.',
      'Click "Generate" and copy the 16-character password.',
      'Paste it as your SMTP Password below.'
    ]
  },
  {
    name: 'Yahoo Mail',
    icon: '💜',
    host: 'smtp.mail.yahoo.com',
    port: '587',
    instructions: [
      'Go to Yahoo Account Info → Account Security.',
      'Enable 2-Step Verification.',
      'Click "Generate App Password".',
      'Select "Other App" and name it "YourInboxHero".',
      'Copy the generated password.',
      'Paste it as your SMTP Password below.'
    ]
  },
  {
    name: 'Outlook / Microsoft 365',
    icon: '🔵',
    host: 'smtp.office365.com',
    port: '587',
    instructions: [
      'Go to Microsoft Account → Security → Advanced Security.',
      'Under "App passwords", click "Create a new app password".',
      'Copy the generated password.',
      'Use your full Outlook email as the SMTP Username.',
      'Paste the app password as your SMTP Password below.'
    ]
  }
];

export const EmailProviders = () => {
  const [selectedProvider, setSelectedProvider] = useState<ProviderConfig | null>(null);
  const [smtpUsername, setSmtpUsername] = useState('');
  const [smtpPassword, setSmtpPassword] = useState('');
  const [smtpFromEmail, setSmtpFromEmail] = useState('');
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const [connectedProvider, setConnectedProvider] = useState('');

  useEffect(() => {
    loadCurrentSettings();
  }, []);

  const loadCurrentSettings = async () => {
    try {
      const data = await getMe();
      if (data.smtp_host) {
        setIsConnected(true);
        const found = PROVIDERS.find(p => p.host === data.smtp_host);
        setConnectedProvider(found ? found.name : data.smtp_host);
        setSmtpUsername(data.smtp_username || '');
        setSmtpFromEmail(data.smtp_from_email || '');
      }
    } catch (err) {
      console.error(err);
    }
  };

  const handleConnect = async () => {
    if (!selectedProvider || !smtpUsername || !smtpPassword) {
      setMessage('Please fill in all fields.');
      return;
    }
    setSaving(true);
    setMessage('');
    try {
      await updateSettings({
        smtp_host: selectedProvider.host,
        smtp_port: selectedProvider.port,
        smtp_username: smtpUsername,
        smtp_password: smtpPassword,
        smtp_from_email: smtpFromEmail || smtpUsername
      });
      setMessage('Email provider connected successfully!');
      setIsConnected(true);
      setConnectedProvider(selectedProvider.name);
    } catch (err: any) {
      setMessage(`Error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleDisconnect = async () => {
    setSaving(true);
    try {
      await updateSettings({
        smtp_host: '',
        smtp_port: '',
        smtp_username: '',
        smtp_password: '',
        smtp_from_email: ''
      });
      setIsConnected(false);
      setConnectedProvider('');
      setSelectedProvider(null);
      setSmtpUsername('');
      setSmtpPassword('');
      setSmtpFromEmail('');
      setMessage('Email provider disconnected. Reminders will now be sent from the system email.');
    } catch (err: any) {
      setMessage(`Error: ${err.message}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
      <h2 style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-primary)' }}>Email Setup</h2>
      <p style={{ color: 'var(--color-text-light)', marginBottom: '24px' }}>
        Connect your email provider so reminders are sent directly from your business email address.
      </p>

      {/* Connection Status */}
      {isConnected && (
        <div style={{ 
          padding: '16px 20px', 
          background: '#f0fdf4', 
          border: '1px solid #bbf7d0', 
          borderRadius: '10px', 
          marginBottom: '24px',
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center'
        }}>
          <div>
            <strong style={{ color: '#166534' }}>✅ Connected</strong>
            <p style={{ color: '#15803d', margin: '4px 0 0', fontSize: '0.9rem' }}>
              Reminders are being sent via <strong>{connectedProvider}</strong>
            </p>
          </div>
          <button 
            onClick={handleDisconnect}
            disabled={saving}
            style={{ 
              background: 'transparent', 
              border: '1px solid #dc2626', 
              color: '#dc2626', 
              padding: '8px 16px', 
              borderRadius: '6px', 
              cursor: 'pointer',
              fontSize: '0.85rem'
            }}
          >
            Disconnect
          </button>
        </div>
      )}

      {/* Provider Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '16px', marginBottom: '24px' }}>
        {PROVIDERS.map((provider) => (
          <div
            key={provider.name}
            onClick={() => { setSelectedProvider(provider); setMessage(''); }}
            style={{
              padding: '24px 16px',
              borderRadius: '12px',
              border: selectedProvider?.name === provider.name ? '2px solid var(--color-primary)' : '1px solid var(--color-border)',
              background: selectedProvider?.name === provider.name ? 'var(--color-bg-alt)' : '#fff',
              cursor: 'pointer',
              textAlign: 'center',
              transition: 'all 0.2s ease'
            }}
          >
            <div style={{ fontSize: '2rem', marginBottom: '8px' }}>{provider.icon}</div>
            <h4 style={{ margin: 0, fontSize: '0.95rem' }}>{provider.name}</h4>
          </div>
        ))}
      </div>

      {/* Setup Instructions & Form */}
      {selectedProvider && (
        <div className="form-container" style={{ animation: 'fadeIn 0.3s ease' }}>
          <h3 style={{ marginBottom: '16px' }}>Connect {selectedProvider.name}</h3>
          
          <div style={{ 
            background: '#fffbeb', 
            border: '1px solid #fde68a', 
            borderRadius: '8px', 
            padding: '16px', 
            marginBottom: '20px' 
          }}>
            <strong style={{ color: '#92400e', fontSize: '0.9rem' }}>📋 Setup Instructions:</strong>
            <ol style={{ margin: '10px 0 0', paddingLeft: '20px', color: '#78350f', fontSize: '0.88rem', lineHeight: '1.8' }}>
              {selectedProvider.instructions.map((step, i) => (
                <li key={i}>{step}</li>
              ))}
            </ol>
          </div>

          <div style={{ display: 'grid', gap: '16px' }}>
            <div className="form-group">
              <label className="form-label">SMTP Host</label>
              <input className="form-input" value={selectedProvider.host} readOnly style={{ background: 'var(--color-bg-alt)', color: 'var(--color-text-light)' }} />
            </div>
            <div className="form-group">
              <label className="form-label">SMTP Port</label>
              <input className="form-input" value={selectedProvider.port} readOnly style={{ background: 'var(--color-bg-alt)', color: 'var(--color-text-light)' }} />
            </div>
            <div className="form-group">
              <label className="form-label">Email Address (Username)</label>
              <input 
                className="form-input" 
                type="email"
                value={smtpUsername} 
                onChange={(e) => setSmtpUsername(e.target.value)} 
                placeholder="billing@yourcompany.com" 
                required 
              />
            </div>
            <div className="form-group">
              <label className="form-label">App Password</label>
              <input 
                className="form-input" 
                type="password"
                value={smtpPassword} 
                onChange={(e) => setSmtpPassword(e.target.value)} 
                placeholder="Paste your app password here" 
                required 
              />
            </div>
            <div className="form-group">
              <label className="form-label">Send From (Optional - defaults to your email)</label>
              <input 
                className="form-input" 
                type="email"
                value={smtpFromEmail} 
                onChange={(e) => setSmtpFromEmail(e.target.value)} 
                placeholder="billing@yourcompany.com" 
              />
            </div>
          </div>

          <div style={{ marginTop: '20px', display: 'flex', gap: '10px' }}>
            <button className="btn-primary" onClick={handleConnect} disabled={saving}>
              {saving ? 'Connecting...' : 'Connect Provider'}
            </button>
            <button 
              onClick={() => setSelectedProvider(null)}
              style={{ background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text)', padding: '10px 20px', borderRadius: '8px', cursor: 'pointer' }}
            >
              Cancel
            </button>
          </div>

          {message && (
            <div style={{ marginTop: '15px', color: message.startsWith('Error') ? 'red' : 'green' }}>
              {message}
            </div>
          )}
        </div>
      )}

      {!selectedProvider && !isConnected && (
        <p style={{ color: 'var(--color-text-light)', textAlign: 'center', padding: '20px', fontSize: '0.9rem' }}>
          Select a provider above to get started. If you don't connect an email provider, reminders will be sent from the default system email.
        </p>
      )}
    </div>
  );
};
