import React, { useState, useEffect } from 'react';
import { getMe, updateSettings } from '../api/invoice';
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
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
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


    </div>
  );
};
