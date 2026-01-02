// Quantum HUB ERP TypeScript Types

export type JobStatus =
  | 'draft'
  | 'quoted'
  | 'scheduled'
  | 'financial_hold'
  | 'in_production'
  | 'completed'
  | 'cancelled';

export type QuoteType = 'fastest' | 'cheapest' | 'balanced';

export type MessageRole = 'user' | 'assistant' | 'system';

export type UIResponseType =
  | 'text'
  | 'quote_options'
  | 'job_status'
  | 'schedule_view'
  | 'inventory_table'
  | 'chart'
  | 'confirmation'
  | 'error'
  | 'estimate_card'
  | 'estimate_list';

// API Response Types

export interface ChatMessage {
  thread_id: string;
  role: MessageRole;
  content: string;
  response_type?: UIResponseType;
  response_data?: Record<string, unknown>;
  created_at: string;
}

export interface ChatInput {
  message: string;
  thread_id?: string;
}

export interface Job {
  id: number;
  job_number: string;
  customer_name: string;
  customer_email?: string;
  description?: string;
  status: JobStatus;
  priority: number;
  quote_id?: number;
  po_number?: string;
  financial_hold: boolean;
  financial_hold_reason?: string;
  requested_delivery_date?: string;
  estimated_delivery_date?: string;
  actual_delivery_date?: string;
  created_at: string;
  updated_at: string;
}

export interface QuoteOption {
  quote_type: QuoteType;
  total_price: number;
  estimated_delivery_date: string;
  lead_time_days: number;
  material_cost: number;
  labor_cost: number;
  overhead_cost: number;
  details: string;
  highlights: string[];
}

export interface QuoteOptionsData {
  customer_name: string;
  product_description?: string;
  quantity?: number;
  inventory_summary?: string;
  schedule_summary?: string;
  options: {
    fastest: QuoteOption;
    cheapest: QuoteOption;
    balanced: QuoteOption;
  };
  synthesis?: string;
}

export interface Item {
  id: number;
  name: string;
  sku: string;
  description?: string;
  quantity_on_hand: number;
  reorder_point: number;
  cost_per_unit: number;
  vendor_lead_time_days: number;
  vendor_name?: string;
  category?: string;
  created_at: string;
  updated_at: string;
}

export interface Machine {
  id: number;
  name: string;
  machine_type: string;
  hourly_rate: number;
  capabilities?: Record<string, unknown>;
  status: string;
  location?: string;
  created_at: string;
  updated_at: string;
}

export interface ProductionSlot {
  id: number;
  machine_id: number;
  job_id?: number;
  start_time: string;
  end_time: string;
  status: string;
  notes?: string;
}

export interface ScheduleData {
  [machineName: string]: {
    machine_id: number;
    hourly_rate: number;
    slots: {
      id: number;
      job_id?: number;
      start: string;
      end: string;
      status: string;
    }[];
  };
}

// Component Props

export interface GenerativeUIProps {
  type: UIResponseType;
  data?: Record<string, unknown>;
  onAction?: (action: string, payload?: unknown) => void;
}

// ============================================================================
// Estimate Types
// ============================================================================

export type EstimateStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'sent'
  | 'accepted'
  | 'rejected'
  | 'expired';

export type ATPStatus = 'available' | 'partial' | 'backorder';

export interface EstimateLineItem {
  id: number;
  estimate_id: number;
  item_id?: number;
  description: string;
  quantity: number;
  unit_price: number;
  discount_pct: number;
  notes?: string;
  list_price?: number;
  unit_cost?: number;
  line_total: number;
  tax_amount: number;
  atp_status?: ATPStatus;
  atp_available_qty?: number;
  atp_shortage_qty?: number;
  atp_lead_time_days?: number;
  sort_order: number;
  created_at: string;
}

export interface Estimate {
  id: number;
  estimate_number: string;
  version: number;
  parent_estimate_id?: number;
  customer_id: number;
  customer_name?: string;
  status: EstimateStatus;
  currency_code: string;
  price_book_id?: number;
  valid_until?: string;
  requested_delivery_date?: string;
  earliest_delivery_date?: string;
  delivery_feasible: boolean;
  notes?: string;
  subtotal: number;
  tax_amount: number;
  total_amount: number;
  margin_percent?: number;
  pending_approvers?: string[];
  approved_by?: number;
  approved_at?: string;
  rejection_reason?: string;
  sent_at?: string;
  accepted_at?: string;
  created_by?: number;
  created_at: string;
  updated_at: string;
  line_items: EstimateLineItem[];
}

export interface EstimateListItem {
  id: number;
  estimate_number: string;
  version: number;
  customer_id: number;
  customer_name?: string;
  status: EstimateStatus;
  total_amount: number;
  valid_until?: string;
  created_at: string;
}

export interface EstimateLineItemCreate {
  item_id?: number;
  description: string;
  quantity: number;
  unit_price: number;
  discount_pct?: number;
  notes?: string;
}

export interface EstimateCardData {
  estimate: Estimate;
  customer?: { id: number; name: string; email?: string };
}

export interface EstimateListData {
  estimates: EstimateListItem[];
  message?: string;
}
