// In production the frontend (Vercel) and backend (a separate host) live on
// different domains, so relative "/api/..." paths would hit Vercel itself.
// VITE_API_BASE_URL points at the real backend (e.g. https://api.yourinboxhero.com);
// left unset, it defaults to same-origin, which is what local dev's Vite
// proxy (vite.config.ts) expects.
export const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

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
  const res = await fetch(`${API_BASE}/api/invoice`, { headers: getAuthHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch invoices');
  // The backend returns a paginated envelope ({items, total, page, ...}),
  // not a bare array — unwrap it so callers always get a plain Invoice[].
  const data = await res.json();
  return data.items ?? data;
};

export const fetchAnalytics = async (): Promise<AnalyticsData> => {
  const res = await fetch(`${API_BASE}/api/analytics`, { headers: getAuthHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch analytics');
  return await res.json();
};


export const pauseInvoice = async (id: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/api/invoice/${id}/pause`, { 
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!res.ok) throw new Error('Failed to pause invoice');
};

export const fetchDebtors = async (): Promise<Debtor[]> => {
  const res = await fetch(`${API_BASE}/api/debtor`, { headers: getAuthHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch debtors');
  // Paginated envelope ({items, total, page, ...}), not a bare array.
  const data = await res.json();
  return data.items ?? data;
};

export const createDebtor = async (data: { name: string; email: string; phone?: string; debtor_type: string }): Promise<Debtor> => {
  const res = await fetch(`${API_BASE}/api/debtor`, {
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
  const res = await fetch(`${API_BASE}/api/debtor/${id}`, {
    method: 'DELETE',
    headers: getAuthHeaders(),
  });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to delete debtor');
};

export const createInvoice = async (data: { debtor_id: string; invoice_number: string; amount: number; due_date: string; description?: string; payment_link?: string; payment_instructions?: string }): Promise<Invoice> => {
  const res = await fetch(`${API_BASE}/api/invoice`, {
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

  const res = await fetch(`${API_BASE}/api/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData.toString()
  });

  if (!res.ok) throw new Error('Invalid credentials');
  const data = await res.json();
  localStorage.setItem('token', data.access_token);
  return data.access_token;
};

export class RegistrationError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export const register = async (username: string, password: string, company_name: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/api/users/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, company_name })
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new RegistrationError(errorData.detail || 'Registration failed', res.status);
  }

  // Auto login after successful registration
  await login(username, password);
};

export const getCompanyName = (): string => {
  const customName = localStorage.getItem('company_name');
  if (customName) return customName;

  const token = localStorage.getItem('token');
  if (!token) return 'YourInboxHero';
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.company_name || 'YourInboxHero';
  } catch (e) {
    return 'YourInboxHero';
  }
};
export const logout = () => {
  localStorage.removeItem('token');
  localStorage.removeItem('company_name');
};

export const downloadInvoicePdf = async (invoiceId: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/api/invoice/${invoiceId}/pdf`, {
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
  const res = await fetch(`${API_BASE}/api/email-template`, { headers: getAuthHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch email templates');
  return await res.json();
};

export const saveEmailTemplate = async (data: { template_type: string; subject: string; body: string }): Promise<EmailTemplate> => {
  const res = await fetch(`${API_BASE}/api/email-template`, {
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

export const getMe = async (): Promise<any> => {
  const token = localStorage.getItem('token');
  if (!token) throw new Error('Not authenticated');

  const res = await fetch(`${API_BASE}/api/users/me`, {
    headers: { 'Authorization': `Bearer ${token}` }
  });

  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch user settings');
  return await res.json();
};

export const updateSettings = async (settings: any): Promise<void> => {
  const token = localStorage.getItem('token');
  if (!token) throw new Error('Not authenticated');

  const res = await fetch(`${API_BASE}/api/users/me`, {
    method: 'PUT',
    headers: { 
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify(settings)
  });

  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to update settings');
};

// ============ Document Collection API ============

export interface DocumentClient {
  id: string;
  name: string;
  email: string;
  phone?: string;
}

export interface DocumentRequest {
  id: string;
  title: string;
  description?: string;
  due_date: string;
  status: string;
  upload_token: string;
  uploaded_file_name?: string;
  escalation_tier: string;
  sms_sent_count: number;
  voice_call_count: number;
  client: DocumentClient;
}

export const getDocumentClients = async (): Promise<DocumentClient[]> => {
  const res = await fetch(`${API_BASE}/api/document-clients`, { headers: getAuthHeaders() });
  if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
  if (!res.ok) throw new Error('Failed to fetch document clients');
  return await res.json();
};

export const createDocumentClient = async (data: Omit<DocumentClient, 'id'>): Promise<DocumentClient> => {
  const res = await fetch(`${API_BASE}/api/document-clients`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create document client');
  }
  return await res.json();
};

export const fetchDocumentRequests = async (): Promise<DocumentRequest[]> => {
  const res = await fetch(`${API_BASE}/api/documents`, { headers: getAuthHeaders() });
  if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
  if (!res.ok) throw new Error('Failed to fetch document requests');
  return await res.json();
};

export const createDocumentRequest = async (data: { client_id: string; title: string; description?: string; due_date: string }): Promise<DocumentRequest> => {
  const res = await fetch(`${API_BASE}/api/documents`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify(data)
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to create document request');
  }
  return await res.json();
};

export const deleteDocumentRequest = async (id: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/api/documents/${id}`, {
    method: 'DELETE',
    headers: getAuthHeaders()
  });
  if (!res.ok) throw new Error('Failed to delete document request');
};

