import React, { useState, useEffect } from 'react';
import { fetchEmailTemplates, saveEmailTemplate, EmailTemplate } from '../api/invoice';
import './Forms.css';
import './InvoiceTable.css';

const EmailTemplates: React.FC = () => {
  const [activeTab, setActiveTab] = useState<'upcoming' | 'due' | 'overdue'>('upcoming');
  const [templates, setTemplates] = useState<{ [key: string]: EmailTemplate | null }>({
    upcoming: null,
    due: null,
    overdue: null
  });
  const [formData, setFormData] = useState({ subject: '', body: '' });
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const loadTemplates = async () => {
    try {
      const data = await fetchEmailTemplates();
      const newTemplates = { upcoming: null, due: null, overdue: null } as any;
      data.forEach(t => {
        if (['upcoming', 'due', 'overdue'].includes(t.template_type)) {
          newTemplates[t.template_type] = t;
        }
      });
      setTemplates(newTemplates);
      
      const activeTemplate = newTemplates[activeTab];
      setFormData({
        subject: activeTemplate ? activeTemplate.subject : '',
        body: activeTemplate ? activeTemplate.body : ''
      });
    } catch (err) {
      console.error(err);
    }
  };

  useEffect(() => {
    loadTemplates();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const activeTemplate = templates[activeTab];
    setFormData({
      subject: activeTemplate ? activeTemplate.subject : '',
      body: activeTemplate ? activeTemplate.body : ''
    });
    setMessage('');
  }, [activeTab, templates]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setMessage('');
    try {
      await saveEmailTemplate({
        template_type: activeTab,
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

  return (
    <div className="email-templates-container" style={{ padding: '20px', maxWidth: '800px', margin: '0 auto' }}>
      <h2 style={{ fontFamily: 'var(--font-heading)', color: 'var(--color-primary)' }}>Email Templates</h2>
      <p style={{ color: 'var(--color-text-light)' }}>Customize the emails sent for each reminder stage.</p>
      
      <div style={{ display: 'flex', gap: '10px', marginBottom: '20px' }}>
        {(['upcoming', 'due', 'overdue'] as const).map(tab => (
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
        <h3 style={{ marginBottom: '15px' }}>{activeTab.charAt(0).toUpperCase() + activeTab.slice(1)} Template</h3>
        <form onSubmit={handleSubmit}>
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
          <div className="form-group">
            <label className="form-label">Body</label>
            <div style={{ fontSize: '0.85rem', color: 'var(--color-text-light)', marginBottom: '8px' }}>
              Available variables: <code style={{ backgroundColor: 'var(--color-bg)', padding: '2px 4px', borderRadius: '4px' }}>{`{{debtor_name}}`}</code>, <code style={{ backgroundColor: 'var(--color-bg)', padding: '2px 4px', borderRadius: '4px' }}>{`{{amount_due}}`}</code>, <code style={{ backgroundColor: 'var(--color-bg)', padding: '2px 4px', borderRadius: '4px' }}>{`{{invoice_number}}`}</code>, <code style={{ backgroundColor: 'var(--color-bg)', padding: '2px 4px', borderRadius: '4px' }}>{`{{due_date}}`}</code>, <code style={{ backgroundColor: 'var(--color-bg)', padding: '2px 4px', borderRadius: '4px' }}>{`{{company_name}}`}</code>
            </div>
            <textarea
              className="form-textarea"
              rows={10}
              value={formData.body}
              onChange={(e) => setFormData({ ...formData, body: e.target.value })}
              required
              style={{ width: '100%', resize: 'vertical' }}
            />
          </div>
          <button type="submit" className="btn-primary" disabled={loading}>
            {loading ? 'Saving...' : 'Save Template'}
          </button>
          {message && <div style={{ marginTop: '15px', color: message.startsWith('Error') ? 'red' : 'green' }}>{message}</div>}
        </form>
      </div>
    </div>
  );
};

export default EmailTemplates;
