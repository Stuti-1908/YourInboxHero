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
  voice_call_consent: boolean;
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
  const res = await fetch(`${API_BASE}/invoice`, { headers: getAuthHeaders() });
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
  const res = await fetch(`${API_BASE}/analytics`, { headers: getAuthHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch analytics');
  return await res.json();
};


export const pauseInvoice = async (id: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/invoice/${id}/pause`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!res.ok) throw new Error('Failed to pause invoice');
};

export const resumeInvoice = async (id: string): Promise<{ status: string }> => {
  const res = await fetch(`${API_BASE}/invoice/${id}/resume`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!res.ok) throw new Error('Failed to resume invoice');
  return await res.json();
};

export const markInvoicePaid = async (id: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/invoice/${id}/mark-paid`, {
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!res.ok) throw new Error('Failed to mark invoice as paid');
};

export const fetchDebtors = async (): Promise<Debtor[]> => {
  const res = await fetch(`${API_BASE}/debtor`, { headers: getAuthHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch debtors');
  // Paginated envelope ({items, total, page, ...}), not a bare array.
  const data = await res.json();
  return data.items ?? data;
};

export const createDebtor = async (data: { name: string; email: string; phone?: string; debtor_type: string; voice_call_consent?: boolean }): Promise<Debtor> => {
  const res = await fetch(`${API_BASE}/debtor`, {
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

export const updateDebtor = async (id: string, data: { name?: string; phone?: string; voice_call_consent?: boolean }): Promise<Debtor> => {
  const res = await fetch(`${API_BASE}/debtor/${id}`, {
    method: 'PUT',
    headers: getAuthHeaders(),
    body: JSON.stringify(data),
  });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Failed to update debtor');
  }
  return await res.json();
};

export const deleteDebtor = async (id: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/debtor/${id}`, {
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
  const res = await fetch(`${API_BASE}/invoice`, {
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

  const res = await fetch(`${API_BASE}/token`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: formData.toString()
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new Error(errorData.detail || 'Invalid credentials');
  }
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

export const register = async (username: string, password: string, company_name: string, invite_code?: string): Promise<{ verification_email_sent: boolean }> => {
  const res = await fetch(`${API_BASE}/users/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password, company_name, invite_code: invite_code || undefined })
  });

  if (!res.ok) {
    const errorData = await res.json().catch(() => ({}));
    throw new RegistrationError(errorData.detail || 'Registration failed', res.status);
  }

  // The account exists but can't log in until the verification link is
  // clicked (see src/api/auth.py's /token check) — no auto-login here.
  const data = await res.json();
  return { verification_email_sent: data.verification_email_sent !== false };
};

export const verifyEmail = async (token: string): Promise<string> => {
  const res = await fetch(`${API_BASE}/users/verify-email?token=${encodeURIComponent(token)}`, {
    method: 'POST',
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || 'Verification failed');
  }
  return data.msg || 'Email verified successfully.';
};

export const resendVerificationEmail = async (username: string): Promise<void> => {
  await fetch(`${API_BASE}/users/resend-verification`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username }),
  });
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
  const res = await fetch(`${API_BASE}/invoice/${invoiceId}/pdf`, {
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
  const res = await fetch(`${API_BASE}/email-template`, { headers: getAuthHeaders() });
  if (res.status === 401) {
    localStorage.removeItem('token');
    window.location.reload();
  }
  if (!res.ok) throw new Error('Failed to fetch email templates');
  return await res.json();
};

export const saveEmailTemplate = async (data: { template_type: string; subject: string; body: string }): Promise<EmailTemplate> => {
  const res = await fetch(`${API_BASE}/email-template`, {
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

  const res = await fetch(`${API_BASE}/users/me`, {
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

  const res = await fetch(`${API_BASE}/users/me`, {
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
  const res = await fetch(`${API_BASE}/document-clients`, { headers: getAuthHeaders() });
  if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
  if (!res.ok) throw new Error('Failed to fetch document clients');
  return await res.json();
};

export const createDocumentClient = async (data: Omit<DocumentClient, 'id'>): Promise<DocumentClient> => {
  const res = await fetch(`${API_BASE}/document-clients`, {
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
  const res = await fetch(`${API_BASE}/documents`, { headers: getAuthHeaders() });
  if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
  if (!res.ok) throw new Error('Failed to fetch document requests');
  return await res.json();
};

export const createDocumentRequest = async (data: { client_id: string; title: string; description?: string; due_date: string }): Promise<DocumentRequest> => {
  const res = await fetch(`${API_BASE}/documents`, {
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
  const res = await fetch(`${API_BASE}/documents/${id}`, {
    method: 'DELETE',
    headers: getAuthHeaders()
  });
  if (!res.ok) throw new Error('Failed to delete document request');
};

export const downloadDocument = async (docId: string, suggestedFileName?: string): Promise<void> => {
  const res = await fetch(`${API_BASE}/documents/${docId}/download`, {
    headers: getAuthHeaders(),
  });
  if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to download document');
  }
  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = suggestedFileName || 'document';
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
};

// ============ Public document upload (no auth — used by the upload page) ============

export interface PublicDocumentRequestInfo {
  title: string;
  description?: string;
  due_date: string;
  status: string;
  business_name: string;
  already_uploaded_file_name?: string;
}

export const fetchUploadRequestInfo = async (token: string): Promise<PublicDocumentRequestInfo> => {
  const res = await fetch(`${API_BASE}/documents/upload/${token}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Invalid or expired upload link');
  }
  return await res.json();
};

export const submitDocumentUpload = async (token: string, file: File): Promise<void> => {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(`${API_BASE}/documents/upload/${token}`, {
    method: 'POST',
    body: formData,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to upload file');
  }
};

// ============ CSV Bulk Import ============

export interface ImportRow {
  row_number: number;
  debtor_name: string;
  debtor_email: string;
  debtor_phone?: string | null;
  invoice_number: string;
  amount: number;
  due_date: string;
  description?: string | null;
  debtor_exists: boolean;
}

export interface ImportRowError {
  row_number: number;
  error: string;
}

export interface ImportPreviewResponse {
  valid_rows: ImportRow[];
  errors: ImportRowError[];
  total_rows: number;
}

export interface ImportCommitResult {
  row_number: number;
  status: 'created' | 'skipped' | 'error';
  detail: string;
  invoice_id?: string | null;
}

export interface ImportCommitResponse {
  results: ImportCommitResult[];
  created_count: number;
  skipped_count: number;
  error_count: number;
}

export const previewInvoiceImport = async (file: File): Promise<ImportPreviewResponse> => {
  const token = localStorage.getItem('token');
  const formData = new FormData();
  formData.append('file', file);

  const res = await fetch(`${API_BASE}/invoice/import/preview`, {
    method: 'POST',
    headers: token ? { 'Authorization': `Bearer ${token}` } : {},
    body: formData,
  });
  if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to parse CSV file');
  }
  return await res.json();
};

export const commitInvoiceImport = async (rows: ImportRow[]): Promise<ImportCommitResponse> => {
  const res = await fetch(`${API_BASE}/invoice/import/commit`, {
    method: 'POST',
    headers: getAuthHeaders(),
    body: JSON.stringify({ rows }),
  });
  if (res.status === 401) { localStorage.removeItem('token'); window.location.reload(); }
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || 'Failed to import rows');
  }
  return await res.json();
};

