export interface Invoice {
  id: string;
  invoice_number: string;
  amount: number;
  due_date: string;
  status: string;
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

export const pauseInvoice = async (id: string): Promise<void> => {
  const res = await fetch(`/api/invoice/${id}/pause`, { 
    method: 'POST',
    headers: getAuthHeaders()
  });
  if (!res.ok) throw new Error('Failed to pause invoice');
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
