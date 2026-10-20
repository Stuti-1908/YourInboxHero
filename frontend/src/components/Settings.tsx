import React, { useState, useEffect } from 'react';
import { getMe, updateSettings, createBillingPortalSession } from '../api/invoice';
import { EmailProviders } from './EmailProviders';
import Templates from './EmailTemplates';
import './Settings.css';
import './Forms.css';

export const Settings = () => {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [billingLoading, setBillingLoading] = useState(false);
  const [subscriptionPlan, setSubscriptionPlan] = useState('');
  const [subscriptionStatus, setSubscriptionStatus] = useState('');

  const [settings, setSettings] = useState({
    company_name: '',
    logo_base64: ''
  });

  const ALL_DAYS: { code: string; label: string }[] = [
    { code: 'mon', label: 'Mon' },
    { code: 'tue', label: 'Tue' },
    { code: 'wed', label: 'Wed' },
    { code: 'thu', label: 'Thu' },
    { code: 'fri', label: 'Fri' },
    { code: 'sat', label: 'Sat' },
    { code: 'sun', label: 'Sun' },
  ];
  const COMMON_TIMEZONES = [
    'America/New_York', 'America/Chicago', 'America/Denver', 'America/Los_Angeles',
    'America/Anchorage', 'Pacific/Honolulu', 'UTC', 'Europe/London', 'Asia/Kolkata',
  ];
  const [voiceCallDays, setVoiceCallDays] = useState<string[]>(['mon', 'tue', 'wed', 'thu', 'fri']);
  const [voiceCallStartHour, setVoiceCallStartHour] = useState(9);
  const [voiceCallEndHour, setVoiceCallEndHour] = useState(17);
  const [voiceCallTimezone, setVoiceCallTimezone] = useState('America/New_York');

  const toggleVoiceCallDay = (code: string) => {
    setVoiceCallDays(prev =>
      prev.includes(code) ? prev.filter(d => d !== code) : [...prev, code]
    );
  };

  useEffect(() => {
    if (loading || !window.location.hash) return;
    document.getElementById(window.location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, [loading]);

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
      setVoiceCallDays(
        (data.voice_call_days || 'mon,tue,wed,thu,fri')
          .split(',')
          .map((d: string) => d.trim())
          .filter(Boolean)
      );
      setVoiceCallStartHour(data.voice_call_start_hour ?? 9);
      setVoiceCallEndHour(data.voice_call_end_hour ?? 17);
      setVoiceCallTimezone(data.voice_call_timezone || 'America/New_York');
      setSubscriptionPlan(data.subscription_plan || '');
      setSubscriptionStatus(data.subscription_status || '');
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
    if (voiceCallDays.length === 0) {
      setMessage('Select at least one day for voice calls.');
      setSaving(false);
      return;
    }
    if (voiceCallStartHour >= voiceCallEndHour) {
      setMessage('Voice call start time must be before end time.');
      setSaving(false);
      return;
    }
    try {
      await updateSettings({
        ...settings,
        voice_call_days: voiceCallDays.join(','),
        voice_call_start_hour: voiceCallStartHour,
        voice_call_end_hour: voiceCallEndHour,
        voice_call_timezone: voiceCallTimezone,
      });
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

  const handleManageBilling = async () => {
    setBillingLoading(true);
    setMessage('');
    try {
      const { portal_url } = await createBillingPortalSession();
      window.location.href = portal_url;
    } catch (err: any) {
      setMessage(err.message || 'Failed to open billing portal');
      setBillingLoading(false);
    }
  };

  if (loading) return <div className="loading">Loading settings...</div>;

  return (
    <div className="settings-container fade-in">
      <div className="settings-header">
        <div>
          <h2>Settings</h2>
          <p>Billing, branding, how reminders are sent, and what they say.</p>
        </div>
      </div>
      
      {message && <div style={{ marginBottom: '20px', padding: '10px', background: 'var(--color-bg-alt)', borderRadius: '8px', color: 'var(--color-primary)' }}>{message}</div>}

      <div className="settings-card">
        <h3>Billing & Subscription</h3>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <p style={{ margin: 0, fontSize: '0.95rem' }}>
              {subscriptionPlan ? (
                <>
                  Current plan: <strong style={{ textTransform: 'capitalize' }}>{subscriptionPlan}</strong>
                  {' · '}
                  <span style={{ textTransform: 'capitalize', color: subscriptionStatus === 'active' ? 'var(--color-status-success, green)' : 'var(--color-text-light)' }}>
                    {subscriptionStatus}
                  </span>
                </>
              ) : (
                'No active subscription'
              )}
            </p>
            <p style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', marginTop: '4px' }}>
              Update your payment method, view invoices, or cancel your subscription.
            </p>
          </div>
          <button type="button" className="btn-secondary" onClick={handleManageBilling} disabled={billingLoading}>
            {billingLoading ? 'Opening...' : 'Manage Billing'}
          </button>
        </div>
      </div>

      <div className="settings-card" style={{ marginTop: '20px' }}>
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
        <h3>Voice Call Hours</h3>
        <p style={{ fontSize: '0.9rem', color: 'var(--color-text-light)' }}>
          Automated voice call escalation will only be placed on the days and hours below, in your chosen timezone.
        </p>

        <div className="form-group" style={{ marginTop: '10px' }}>
          <label className="form-label">Days</label>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {ALL_DAYS.map(({ code, label }) => {
              const active = voiceCallDays.includes(code);
              return (
                <button
                  type="button"
                  key={code}
                  onClick={() => toggleVoiceCallDay(code)}
                  className={active ? 'btn-primary' : 'btn-secondary'}
                  style={{ padding: '6px 14px', fontSize: '0.85rem' }}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>

        <div style={{ display: 'flex', gap: '15px', marginTop: '15px', flexWrap: 'wrap' }}>
          <div className="form-group" style={{ flex: '1', minWidth: '140px' }}>
            <label className="form-label">Start Hour</label>
            <select
              className="form-input"
              value={voiceCallStartHour}
              onChange={(e) => setVoiceCallStartHour(Number(e.target.value))}
            >
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>{h.toString().padStart(2, '0')}:00</option>
              ))}
            </select>
          </div>
          <div className="form-group" style={{ flex: '1', minWidth: '140px' }}>
            <label className="form-label">End Hour</label>
            <select
              className="form-input"
              value={voiceCallEndHour}
              onChange={(e) => setVoiceCallEndHour(Number(e.target.value))}
            >
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>{h.toString().padStart(2, '0')}:00</option>
              ))}
            </select>
          </div>
          <div className="form-group" style={{ flex: '1', minWidth: '180px' }}>
            <label className="form-label">Timezone</label>
            <select
              className="form-input"
              value={voiceCallTimezone}
              onChange={(e) => setVoiceCallTimezone(e.target.value)}
            >
              {COMMON_TIMEZONES.map(tz => (
                <option key={tz} value={tz}>{tz}</option>
              ))}
            </select>
          </div>
        </div>
        <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn-primary" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save branding & call hours'}
          </button>
        </div>
      </div>

      <div className="settings-card" id="email" style={{ marginTop: '20px' }}>
        <EmailProviders embedded />
      </div>

      <div className="settings-card" id="templates" style={{ marginTop: '20px' }}>
        <Templates embedded />
      </div>
    </div>
  );
};
