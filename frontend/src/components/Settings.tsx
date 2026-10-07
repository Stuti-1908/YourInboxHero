import React, { useState, useEffect } from 'react';
import { getMe, updateSettings, API_BASE } from '../api/invoice';
import './Settings.css';
import './Forms.css';

export const Settings = () => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  const [settings, setSettings] = useState({
    company_name: '',
    logo_base64: ''
  });

  // GHL webhook config is kept separate from `settings` above: webhook_secret
  // is read-only (server-generated, shown so the user can paste it into GHL),
  // and ghl_webhook_signing_secret is write-only (never returned by the API
  // once set -- see GET /users/me's comment on why) and must not be clobbered
  // by the unrelated company-name/logo save below if left blank.
  const [webhookSecret, setWebhookSecret] = useState('');
  const [ghlSignatureConfigured, setGhlSignatureConfigured] = useState(false);
  const [ghlSigningSecretInput, setGhlSigningSecretInput] = useState('');
  const [ghlSaving, setGhlSaving] = useState(false);
  const [ghlMessage, setGhlMessage] = useState('');
  const [urlCopied, setUrlCopied] = useState(false);

  useEffect(() => {
    fetchSettings();
  }, []);

  const fetchSettings = async () => {
    try {
      const data = await getMe();
      if (data.company_name) {
        localStorage.setItem('company_name', data.company_name);
      }
      setSettings({
        company_name: data.company_name || '',
        logo_base64: data.logo_base64 || ''
      });
      setWebhookSecret(data.webhook_secret || '');
      setGhlSignatureConfigured(!!data.ghl_signature_verification_configured);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const ghlWebhookUrl = webhookSecret ? `${API_BASE}/api/webhooks/ghl/${webhookSecret}` : '';

  const handleCopyWebhookUrl = async () => {
    try {
      await navigator.clipboard.writeText(ghlWebhookUrl);
      setUrlCopied(true);
      setTimeout(() => setUrlCopied(false), 2000);
    } catch (err) {
      // Clipboard API can be unavailable (e.g. non-HTTPS or denied
      // permission) -- the URL is still visible and selectable in the
      // input, so this is a convenience failure, not a blocker.
    }
  };

  const handleSaveGhlSecret = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ghlSigningSecretInput.trim()) return;
    setGhlSaving(true);
    setGhlMessage('');
    try {
      await updateSettings({ ghl_webhook_signing_secret: ghlSigningSecretInput.trim() });
      setGhlSignatureConfigured(true);
      setGhlSigningSecretInput('');
      setGhlMessage('Signing secret saved.');
    } catch (err: any) {
      setGhlMessage(err.message || 'Failed to save signing secret');
    } finally {
      setGhlSaving(false);
    }
  };

  const handleRemoveGhlSecret = async () => {
    if (!confirm('Remove the GHL signature verification secret? Inbound webhooks will no longer have their signature checked.')) return;
    setGhlSaving(true);
    setGhlMessage('');
    try {
      await updateSettings({ ghl_webhook_signing_secret: '' });
      setGhlSignatureConfigured(false);
      setGhlMessage('Signing secret removed.');
    } catch (err: any) {
      setGhlMessage(err.message || 'Failed to remove signing secret');
    } finally {
      setGhlSaving(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSettings(prev => ({ ...prev, [e.target.name]: e.target.value }));
  };

  const handleLogoUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onloadend = () => {
        setSettings(prev => ({ ...prev, logo_base64: reader.result as string }));
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setMessage('');
    try {
      await updateSettings(settings);
      setMessage('Settings updated successfully!');
      if (settings.company_name) {
        localStorage.setItem('company_name', settings.company_name);
      }
      setTimeout(() => window.location.reload(), 1500);
    } catch (err: any) {
      setMessage(err.message || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return <div className="loading">Loading settings...</div>;

  return (
    <div className="settings-container fade-in">
      <div className="settings-header">
        <div>
          <h2>Account Settings</h2>
          <p>White-label your experience with your brand identity.</p>
        </div>
        <button className="btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
      
      {message && <div style={{ marginBottom: '20px', padding: '10px', background: 'var(--color-bg-alt)', borderRadius: '8px', color: 'var(--color-primary)' }}>{message}</div>}

      <div className="settings-card">
        <h3>Branding</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '15px' }}>
          <div className="form-group">
            <label className="form-label">Company Name</label>
            <input name="company_name" value={settings.company_name} onChange={handleChange} placeholder="Your Business Name" className="form-input" />
          </div>
          <div className="form-group">
            <label className="form-label">Company Logo (For PDF Invoices)</label>
            <input type="file" accept="image/png, image/jpeg" onChange={handleLogoUpload} className="form-input" />
            {settings.logo_base64 && (
              <div style={{ marginTop: '10px' }}>
                <img src={settings.logo_base64} alt="Logo Preview" style={{ maxHeight: '60px', objectFit: 'contain' }} />
              </div>
            )}
          </div>
        </div>
      </div>

      <div className="settings-card" style={{ marginTop: '20px' }}>
        <h3>Email Provider</h3>
        <p style={{ fontSize: '0.9rem', color: 'var(--color-text-light)' }}>
          To connect or change your email provider, go to the <strong>Email Setup</strong> tab in the navigation bar.
        </p>
      </div>

      <div className="settings-card" style={{ marginTop: '20px' }}>
        <h3>GoHighLevel (GHL) Integration</h3>
        <p style={{ fontSize: '0.9rem', color: 'var(--color-text-light)' }}>
          Paste this URL into your GHL workflow's webhook action to create invoices automatically from GHL. Optionally add a signing secret so YourInboxHero can verify webhooks really came from GHL.
        </p>

        {webhookSecret ? (
          <div className="form-group" style={{ marginTop: '10px' }}>
            <label className="form-label">Your GHL Webhook URL</label>
            <div style={{ display: 'flex', gap: '10px' }}>
              <input
                type="text"
                readOnly
                value={ghlWebhookUrl}
                onFocus={(e) => e.target.select()}
                className="form-input"
                style={{ fontFamily: 'monospace', fontSize: '0.85rem' }}
              />
              <button type="button" className="btn-secondary" onClick={handleCopyWebhookUrl}>
                {urlCopied ? 'Copied!' : 'Copy'}
              </button>
            </div>
          </div>
        ) : (
          <p style={{ fontSize: '0.85rem', color: 'var(--color-text-light)' }}>
            Your webhook URL isn't available yet — try reloading this page.
          </p>
        )}

        <form onSubmit={handleSaveGhlSecret} style={{ marginTop: '15px' }}>
          <div className="form-group">
            <label className="form-label">
              Signing Secret {ghlSignatureConfigured && <span style={{ color: 'var(--color-brand-primary)', fontWeight: 400 }}>(configured)</span>}
            </label>
            <div style={{ display: 'flex', gap: '10px' }}>
              <input
                type="password"
                value={ghlSigningSecretInput}
                onChange={(e) => setGhlSigningSecretInput(e.target.value)}
                placeholder={ghlSignatureConfigured ? 'Enter a new secret to replace it' : 'Paste the signing secret from your GHL workflow'}
                className="form-input"
                autoComplete="off"
              />
              <button type="submit" className="btn-primary" disabled={ghlSaving || !ghlSigningSecretInput.trim()}>
                {ghlSaving ? 'Saving...' : 'Save'}
              </button>
              {ghlSignatureConfigured && (
                <button type="button" className="btn-secondary" onClick={handleRemoveGhlSecret} disabled={ghlSaving}>
                  Remove
                </button>
              )}
            </div>
            <p style={{ fontSize: '0.8rem', color: 'var(--color-text-light)', marginTop: '6px' }}>
              {ghlSignatureConfigured
                ? 'Webhooks without a valid signature are currently rejected.'
                : "Without a signing secret, webhook signatures aren't checked — anyone with your webhook URL above could send fake invoices. Recommended for production use."}
            </p>
          </div>
        </form>

        {ghlMessage && (
          <div style={{ marginTop: '10px', padding: '10px', background: 'var(--color-bg-primary)', borderRadius: '8px', color: 'var(--color-brand-primary)' }}>
            {ghlMessage}
          </div>
        )}
      </div>
    </div>
  );
};
