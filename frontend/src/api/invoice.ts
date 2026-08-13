export interface Invoice {
  id: string;
  invoice_number: string;
  amount: number;
  due_date: string;
  status: string;
}

export const fetchInvoices = async (): Promise<Invoice[]> => {
  const res = await fetch('/api/invoice');
  if (!res.ok) {
    throw new Error('Failed to fetch invoices');
  }
  return await res.json();
};

export const pauseInvoice = async (id: string): Promise<void> => {
  const res = await fetch(`/api/invoice/${id}/pause`, { method: 'POST' });
  if (!res.ok) {
    throw new Error('Failed to pause invoice');
  }
};
