import React, { useState, useEffect } from 'react';
import { fetchEmailTemplates, saveEmailTemplate } from '../api/invoice';
import type { EmailTemplate } from '../api/invoice';
import './Forms.css';
import './InvoiceTable.css';

const DEFAULT_EMAIL_TEMPLATES: Record<string, { subject: string; body: string }> = {
  upcoming: {
    subject: 'Upcoming Invoice #{{invoice_number}} from {{company_name}}',
    body: 'Hi {{debtor_name}},\n\nThis is a friendly heads-up that Invoice #{{invoice_number}} for {{amount_due}} is due on {{due_date}}.\n\nPlease let us know if you have any questions before the due date.\n\nPay here: {{payment_link}}\n\nBest regards,\n{{company_name}}'
  },
  due: {
    subject: 'Invoice #{{invoice_number}} is due today',
    body: 'Hi {{debtor_name}},\n\nThis is a quick reminder that Invoice #{{invoice_number}} for {{amount_due}} is due today ({{due_date}}).\n\nPlease arrange for payment as soon as possible.\n\nPay here: {{payment_link}}\n\nThank you,\n{{company_name}}'
  },
  overdue: {
    subject: 'URGENT: Invoice #{{invoice_number}} is OVERDUE',
    body: 'Hi {{debtor_name}},\n\nOur records indicate that Invoice #{{invoice_number}} for {{amount_due}} was due on {{due_date}} and is now overdue.\n\nPlease submit your payment immediately to avoid any late fees or interruptions in service.\n\nPay now: {{payment_link}}\n\nRegards,\n{{company_name}}'
  }
};

const DEFAULT_SMS_TEMPLATES: Record<string, { subject: string; body: string }> = {
  upcoming: {
    subject: 'Upcoming Invoice',
    body: 'Hi {{debtor_name}}, Invoice #{{invoice_number}} for {{amount_due}} from {{company_name}} is due on {{due_date}}. Pay here: {{payment_link}}'
  },
  due: {
    subject: 'Invoice Due Today',
    body: 'Hi {{debtor_name}}, your Invoice #{{invoice_number}} for {{amount_due}} is due TODAY. Please pay now: {{payment_link}} - {{company_name}}'
  },
  overdue: {
    subject: 'OVERDUE Invoice',
    body: 'URGENT: {{debtor_name}}, Invoice #{{invoice_number}} for {{amount_due}} is OVERDUE (was due {{due_date}}). Pay immediately: {{payment_link}} - {{company_name}}'
  }
};

const Templates: React.FC<{ embedded?: boolean }> = ({ embedded = false }) => {
  const [medium, setMedium] = useState<'email' | 'sms'>('email');
  const [activeTab, setActiveTab] = useState<'upcoming' | 'due' | 'overdue'>('upcoming');
  // Saved templates keyed by backend template_type: email stages use the
  // bare stage name, SMS stages are prefixed "sms_".
  const [templates, setTemplates] = useState<Record<string, EmailTemplate>>({});
  const [formData, setFormData] = useState({ subject: '', body: '' });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const getDefaults = () => medium === 'email' ? DEFAULT_EMAIL_TEMPLATES : DEFAULT_SMS_TEMPLATES;
  const templateKey = medium === 'sms' ? `sms_${activeTab}` : activeTab;

  const loadTemplates = async () => {
    try {
      const data = await fetchEmailTemplates();
      const byType: Record<string, EmailTemplate> = {};
      data.forEach((t: EmailTemplate) => { byType[t.template_type] = t; });
      setTemplates(byType);
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadTemplates();
  }, []);

  useEffect(() => {
    const saved = templates[templateKey];
    const defaults = getDefaults();
    setFormData({
      subject: saved ? saved.subject : defaults[activeTab].subject,
      body: saved ? saved.body : defaults[activeTab].body
    });
    setMessage('');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [templateKey, templates]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setMessage('');
    try {
      await saveEmailTemplate({
        template_type: templateKey,
        subject: formData.subject,
        body: formData.body
      });
      setMessage('Template saved successfully!');
      await loadTemplates();
    } catch (err: any) {
      setMessage(`Error: ${err.message}`);
    } finally {
      setLoading(false);
    }
  };

  const defaults = getDefaults();

  return (
    <div className="email-templates-container" style={embedded ? undefined : { padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
      {embedded ? <h3>Reminder Templates</h3> : <h2 style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-primary)' }}>Templates</h2>}
      <p style={{ color: 'var(--color-text-light)' }}>Customize the messages sent for each reminder stage. Available on the Growth and Scale plans.</p>
      
      {/* Medium Toggle */}
      <div style={{ display: 'flex', gap: '0', marginBottom: '24px', borderRadius: '8px', overflow: 'hidden', border: '1px solid var(--color-border)', width: 'fit-content' }}>
        <button
          onClick={() => setMedium('email')}
          style={{
            padding: '10px 24px',
            border: 'none',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.9rem',
            backgroundColor: medium === 'email' ? 'var(--color-primary)' : 'transparent',
            color: medium === 'email' ? '#fff' : 'var(--color-text)'
          }}
        >
          Email
        </button>
        <button
          onClick={() => { setMedium('sms'); setActiveTab('overdue'); }}
          style={{
            padding: '10px 24px',
            border: 'none',
            borderLeft: '1px solid var(--color-border)',
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: '0.9rem',
            backgroundColor: medium === 'sms' ? 'var(--color-primary)' : 'transparent',
            color: medium === 'sms' ? '#fff' : 'var(--color-text)'
          }}
        >
          SMS
        </button>
      </div>

      {medium === 'sms' && (
        <p style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', marginTop: '-12px', marginBottom: '16px' }}>
          Text messages are only sent once an invoice is overdue, so there is one SMS template.
        </p>
      )}

      {/* Stage Tabs */}
      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', flexWrap: 'wrap' }}>
        {(medium === 'sms' ? (['overdue'] as const) : (['upcoming', 'due', 'overdue'] as const)).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`btn-primary ${activeTab === tab ? '' : 'btn-outline'}`}
            style={activeTab !== tab ? { backgroundColor: 'transparent', color: 'var(--color-primary)', border: '1px solid var(--color-primary)' } : {}}
          >
            {tab.charAt(0).toUpperCase() + tab.slice(1)}
          </button>
        ))}
      </div>

      <div className="form-container">
        <h3 style={{ marginBottom: '15px' }}>
          {activeTab.charAt(0).toUpperCase() + activeTab.slice(1)} {medium === 'email' ? 'Email' : 'SMS'} Template
        </h3>
        <form onSubmit={handleSubmit}>
          {medium === 'email' && (
            <div className="form-group">
              <label className="form-label">Subject</label>
              <input
                type="text"
                className="form-input"
                value={formData.subject}
                onChange={(e) => setFormData({ ...formData, subject: e.target.value })}
                required
              />
            </div>
          )}
          <div className="form-group">
            <label className="form-label">{medium === 'email' ? 'Body' : 'Message'}</label>
            <div style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', marginBottom: '8px', lineHeight: 1.9, overflowWrap: 'anywhere' }}>
              Available variables: <code style={{ backgroundColor: 'var(--color-bg)', padding: '2px 4px', borderRadius: '4px' }}>{`{{debtor_name}}`}</code>, <code style={{ backgroundColor: 'var(--color-bg)', padding: '2px 4px', borderRadius: '4px' }}>{`{{amount_due}}`}</code>, <code style={{ backgroundColor: 'var(--color-bg)', padding: '2px 4px', borderRadius: '4px' }}>{`{{invoice_number}}`}</code>, <code style={{ backgroundColor: 'var(--color-bg)', padding: '2px 4px', borderRadius: '4px' }}>{`{{due_date}}`}</code>, <code style={{ backgroundColor: 'var(--color-bg)', padding: '2px 4px', borderRadius: '4px' }}>{`{{company_name}}`}</code>, <code style={{ backgroundColor: 'var(--color-bg)', padding: '2px 4px', borderRadius: '4px' }}>{`{{payment_link}}`}</code>
            </div>
            <textarea
              className="form-textarea"
              rows={medium === 'sms' ? 4 : 10}
              value={formData.body}
              onChange={(e) => setFormData({ ...formData, body: e.target.value })}
              required
              style={{ width: '100%', resize: 'vertical' }}
              maxLength={medium === 'sms' ? 320 : undefined}
            />
            {medium === 'sms' && (
              <small style={{ color: 'var(--color-text-light)', fontSize: '0.8rem' }}>
                {formData.body.length}/320 characters
              </small>
            )}
          </div>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <button type="submit" className="btn-primary" disabled={loading}>
              {loading ? 'Saving...' : 'Save Template'}
            </button>
            <button 
              type="button" 
              className="btn-secondary" 
              onClick={() => {
                setFormData({
                  subject: defaults[activeTab].subject,
                  body: defaults[activeTab].body
                });
                setMessage('Restored to default values (Unsaved)');
              }}
              style={{ background: 'transparent', border: '1px solid var(--color-border)', color: 'var(--color-text)' }}
            >
              Restore Default
            </button>
          </div>
          {message && <div style={{ marginTop: '15px', color: message.startsWith('Error') ? 'red' : 'green' }}>{message}</div>}
        </form>
      </div>
    </div>
  );
};

export default Templates;
