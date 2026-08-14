export interface Invoice {
  id: string;
  invoice_number: string;
  amount: number;
  due_date: string;
  status: string;
}

export interface AnalyticsData {
  total_outstanding: number;
  total_recovered: number;
  recovery_rate: number;
  aging: {
    current: number;
    days_30: number;
    days_60: number;
    days_90_plus: number;
  };
  status_breakdown: Record<string, number>;
  monthly_recovered: { month: string; amount: number }[];
}


export interface Debtor {
  id: string;
  name: string;
  email: string;
  phone?: string;
  debtor_type: string;
}

export interface EmailTemplate {
  id: string;
  template_type: string;
  subject: string;
  body: string;
}

const getAuthHeaders = () => {
  const token = localStorage.getItem('token');
  return {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {})
  };
};

export const fetchInvoices = async (): Promise<Invoice[]> => {
  const res = await fetch('/api/invoice', { headers: getAuthHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch invoices');
  return await res.json();
};

export const fetchAnalytics = async (): Promise<AnalyticsData> => {
  const res = await fetch('/api/analytics', { headers: getAuthHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch analytics');
  return await res.json();
};


export const pauseInvoice = async (id: string): Promise<void> => {
  const res = await fetch(`/api/invoice/${id}/pause`, { 
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!res.ok) throw new Error('Failed to pause invoice');
};

export const fetchDebtors = async (): Promise<Debtor[]> => {
  const res = await fetch('/api/debtor', { headers: getAuthHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch debtors');
  return await res.json();
};

export const createDebtor = async (data: { name: string; email: string; phone?: string; debtor_type: string }): Promise<Debtor> => {
  const res = await fetch('/api/debtor', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) {
    const errorData = await res.json();
    throw new Error(errorData.detail || 'Failed to create debtor');
  }
  return await res.json();
};

export const deleteDebtor = async (id: string): Promise<void> => {
  const res = await fetch(`/api/debtor/${id}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to delete debtor');
};

export const createInvoice = async (data: { debtor_id: string; invoice_number: string; amount: number; due_date: string; description?: string; payment_instructions?: string }): Promise<Invoice> => {
  const res = await fetch('/api/invoice', {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to create invoice');
  }
  return await res.json();
};

export const login = async (username: string, password: string): Promise<string> => {
  const formData = new URLSearchParams();
  formData.append('username', username);
  formData.append('password', password);

  const res = await fetch('/api/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData.toString()
  });

  if (!res.ok) throw new Error('Invalid credentials');
  const data = await res.json();
  localStorage.setItem('token', data.access_token);
  return data.access_token;
};

export const logout = () => {
  localStorage.removeItem('token');
  window.location.reload();
};

export const downloadInvoicePdf = async (invoiceId: string): Promise<void> => {
  const res = await fetch(`/api/invoice/${invoiceId}/pdf`, {
    headers: getAuthHeaders()
  });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to download PDF');
  
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `invoice_${invoiceId}.pdf`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
};

export const fetchEmailTemplates = async (): Promise<EmailTemplate[]> => {
  const res = await fetch('/api/email-template', { headers: getAuthHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch email templates');
  return await res.json();
};

export const saveEmailTemplate = async (data: { template_type: string; subject: string; body: string }): Promise<EmailTemplate> => {
  const res = await fetch('/api/email-template', {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to save email template');
  }
  return await res.json();
};
