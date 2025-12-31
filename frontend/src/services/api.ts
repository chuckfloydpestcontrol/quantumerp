// Quantum HUB ERP API Service

const API_BASE = '/api';

interface ApiResponse<T> {
  data?: T;
  error?: string;
}

async function request<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<ApiResponse<T>> {
  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers,
      },
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      return { error: errorData.detail || `HTTP ${response.status}` };
    }

    const data = await response.json();
    return { data };
  } catch (error) {
    return { error: error instanceof Error ? error.message : 'Unknown error' };
  }
}

// Chat API
export const chatApi = {
  send: async (message: string, threadId?: string) =>
    request<{
      thread_id: string;
      role: string;
      content: string;
      response_type?: string;
      response_data?: Record<string, unknown>;
      created_at: string;
    }>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, thread_id: threadId }),
    }),
};

// Jobs API
export const jobsApi = {
  list: async (status?: string) =>
    request<Array<Record<string, unknown>>>(
      `/jobs${status ? `?status=${status}` : ''}`
    ),

  get: async (id: number) => request<Record<string, unknown>>(`/jobs/${id}`),

  create: async (data: Record<string, unknown>) =>
    request<Record<string, unknown>>('/jobs', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  createDynamic: async (data: Record<string, unknown>) =>
    request<Record<string, unknown>>('/jobs/dynamic', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  update: async (id: number, data: Record<string, unknown>) =>
    request<Record<string, unknown>>(`/jobs/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  attachPo: async (id: number, poNumber: string) =>
    request<Record<string, unknown>>(
      `/jobs/${id}/attach-po?po_number=${encodeURIComponent(poNumber)}`,
      { method: 'POST' }
    ),

  acceptQuote: async (id: number, quoteType: string) =>
    request<Record<string, unknown>>(
      `/jobs/${id}/accept-quote?quote_type=${quoteType}`,
      { method: 'POST' }
    ),
};

// Inventory API
export const inventoryApi = {
  list: async (category?: string) =>
    request<Array<Record<string, unknown>>>(
      `/items${category ? `?category=${category}` : ''}`
    ),

  get: async (id: number) => request<Record<string, unknown>>(`/items/${id}`),

  checkStock: async (id: number, quantity: number) =>
    request<Record<string, unknown>>(
      `/items/check-stock/${id}?quantity=${quantity}`
    ),

  getLowStock: async () =>
    request<Array<Record<string, unknown>>>('/inventory/low-stock'),
};

// Machines API
export const machinesApi = {
  list: async () => request<Array<Record<string, unknown>>>('/machines'),

  create: async (data: Record<string, unknown>) =>
    request<Record<string, unknown>>('/machines', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// Schedule API
export const scheduleApi = {
  get: async (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.set('start_date', startDate);
    if (endDate) params.set('end_date', endDate);
    const query = params.toString();
    return request<Record<string, unknown>>(
      `/schedule${query ? `?${query}` : ''}`
    );
  },

  findSlot: async (machineType: string, durationHours: number) =>
    request<Record<string, unknown>>(
      `/schedule/find-slot?machine_type=${machineType}&duration_hours=${durationHours}`
    ),
};

// Quotes API
export const quotesApi = {
  list: async () => request<Array<Record<string, unknown>>>('/quotes'),

  calculate: async (data: {
    bom: Array<{ item_id: number; quantity: number }>;
    labor_hours: number;
    machine_id?: number;
    expedited?: boolean;
  }) =>
    request<Record<string, unknown>>('/quotes/calculate', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  parallel: async (data: {
    bom: Array<{ item_id: number; quantity: number }>;
    labor_hours: number;
    machine_id?: number;
  }) =>
    request<Record<string, unknown>>('/quotes/parallel', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
};

// System API
export const systemApi = {
  health: async () => request<{ status: string }>('/health'),

  status: async () => request<Record<string, unknown>>('/status'),

  seed: async () =>
    request<Record<string, unknown>>('/seed', { method: 'POST' }),
};
