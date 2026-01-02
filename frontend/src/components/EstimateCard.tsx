import React, { useState } from 'react';
import {
  FileText,
  Trash2,
  Plus,
  Send,
  CheckCircle,
  Clock,
  AlertTriangle,
  Package,
  XCircle,
} from 'lucide-react';
import { Estimate, EstimateLineItem, EstimateStatus, ATPStatus } from '../types';

interface EstimateCardProps {
  estimate: Estimate;
  onAddLine?: () => void;
  onDeleteLine?: (lineId: number) => void;
  onAction?: (action: string) => void;
  onRefresh?: () => void;
}

const STATUS_CONFIG: Record<EstimateStatus, { color: string; bg: string; border: string; label: string }> = {
  draft: { color: 'text-yellow-700', bg: 'bg-yellow-100', border: 'border-yellow-500', label: 'Draft' },
  pending_approval: { color: 'text-orange-700', bg: 'bg-orange-100', border: 'border-orange-500', label: 'Pending Approval' },
  approved: { color: 'text-green-700', bg: 'bg-green-100', border: 'border-green-500', label: 'Approved' },
  sent: { color: 'text-blue-700', bg: 'bg-blue-100', border: 'border-blue-500', label: 'Sent' },
  accepted: { color: 'text-green-700', bg: 'bg-green-100', border: 'border-green-500', label: 'Accepted' },
  rejected: { color: 'text-red-700', bg: 'bg-red-100', border: 'border-red-500', label: 'Rejected' },
  expired: { color: 'text-gray-700', bg: 'bg-gray-100', border: 'border-gray-500', label: 'Expired' },
};

const ATP_CONFIG: Record<ATPStatus, { icon: typeof CheckCircle; color: string; label: string }> = {
  available: { icon: CheckCircle, color: 'text-green-600', label: 'In Stock' },
  partial: { icon: AlertTriangle, color: 'text-yellow-600', label: 'Partial' },
  backorder: { icon: Clock, color: 'text-red-600', label: 'Backorder' },
};

function formatCurrency(amount: number, currency = 'USD'): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency,
  }).format(amount);
}

function formatDate(dateStr?: string): string {
  if (!dateStr) return 'N/A';
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function ATPBadge({ status, leadTime }: { status?: ATPStatus; leadTime?: number }) {
  if (!status) return null;
  const config = ATP_CONFIG[status] || ATP_CONFIG.available;
  const Icon = config.icon;
  return (
    <div className={`flex items-center gap-1 text-xs ${config.color}`}>
      <Icon size={12} />
      <span>{config.label}</span>
      {status === 'backorder' && leadTime && (
        <span className="text-gray-500">({leadTime}d)</span>
      )}
    </div>
  );
}

function LineItemRow({
  item,
  index,
  isDraft,
  onDelete,
}: {
  item: EstimateLineItem;
  index: number;
  isDraft: boolean;
  onDelete?: (id: number) => void;
}) {
  return (
    <tr className="border-b border-gray-100 hover:bg-gray-50">
      <td className="px-3 py-2 text-sm text-gray-500">{index + 1}</td>
      <td className="px-3 py-2">
        <div className="text-sm font-medium text-gray-900">{item.description}</div>
        {item.notes && (
          <div className="text-xs text-gray-500 mt-0.5">{item.notes}</div>
        )}
      </td>
      <td className="px-3 py-2 text-sm text-right">{item.quantity}</td>
      <td className="px-3 py-2 text-sm text-right">
        {formatCurrency(item.unit_price)}
        {item.discount_pct > 0 && (
          <span className="text-xs text-green-600 ml-1">-{(item.discount_pct * 100).toFixed(0)}%</span>
        )}
      </td>
      <td className="px-3 py-2 text-sm text-right font-medium">
        {formatCurrency(item.line_total)}
      </td>
      <td className="px-3 py-2">
        <ATPBadge status={item.atp_status} leadTime={item.atp_lead_time_days} />
      </td>
      <td className="px-3 py-2 text-center">
        {isDraft && onDelete && (
          <button
            onClick={() => onDelete(item.id)}
            className="text-gray-400 hover:text-red-600 transition-colors p-1"
            title="Delete line"
          >
            <Trash2 size={14} />
          </button>
        )}
      </td>
    </tr>
  );
}

function ActionButton({
  status,
  onAction,
}: {
  status: EstimateStatus;
  onAction?: (action: string) => void;
}) {
  const config: Record<string, { action: string; label: string; icon: typeof Send; color: string }> = {
    draft: { action: 'submit', label: 'Submit for Approval', icon: Send, color: 'bg-quantum-500 hover:bg-quantum-600' },
    pending_approval: { action: 'approve', label: 'Approve', icon: CheckCircle, color: 'bg-green-500 hover:bg-green-600' },
    approved: { action: 'send', label: 'Send to Customer', icon: Send, color: 'bg-blue-500 hover:bg-blue-600' },
    sent: { action: 'accept', label: 'Mark Accepted', icon: CheckCircle, color: 'bg-green-500 hover:bg-green-600' },
  };

  const cfg = config[status];
  if (!cfg) return null;

  const Icon = cfg.icon;
  return (
    <button
      onClick={() => onAction?.(cfg.action)}
      className={`flex items-center gap-2 px-4 py-2 text-white rounded-lg ${cfg.color} transition-colors`}
    >
      <Icon size={16} />
      {cfg.label}
    </button>
  );
}

export function EstimateCard({
  estimate,
  onAddLine,
  onDeleteLine,
  onAction,
}: EstimateCardProps) {
  const statusConfig = STATUS_CONFIG[estimate.status] || STATUS_CONFIG.draft;
  const isDraft = estimate.status === 'draft';
  const hasATPWarning = estimate.line_items.some(
    (item) => item.atp_status && item.atp_status !== 'available'
  );

  return (
    <div className={`card border-l-4 ${statusConfig.border}`}>
      {/* Header */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-quantum-50 flex items-center justify-center">
            <FileText className="text-quantum-600" size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono text-lg font-semibold text-gray-900">
                {estimate.estimate_number}
              </span>
              {estimate.version > 1 && (
                <span className="text-xs bg-gray-100 text-gray-600 px-2 py-0.5 rounded">
                  v{estimate.version}
                </span>
              )}
            </div>
            <div className="text-sm text-gray-500">
              {estimate.customer_name || `Customer #${estimate.customer_id}`}
            </div>
          </div>
        </div>
        <span className={`px-3 py-1 text-sm font-medium rounded-full ${statusConfig.bg} ${statusConfig.color}`}>
          {statusConfig.label}
        </span>
      </div>

      {/* Info Row */}
      <div className="flex flex-wrap gap-4 mb-4 text-sm">
        <div className="flex items-center gap-1.5 text-gray-600">
          <Clock size={14} />
          <span>Valid until: {formatDate(estimate.valid_until)}</span>
        </div>
        {estimate.earliest_delivery_date && (
          <div className="flex items-center gap-1.5 text-gray-600">
            <Package size={14} />
            <span>Earliest delivery: {formatDate(estimate.earliest_delivery_date)}</span>
          </div>
        )}
        {hasATPWarning && (
          <div className="flex items-center gap-1.5 text-yellow-600">
            <AlertTriangle size={14} />
            <span>Some items have limited availability</span>
          </div>
        )}
      </div>

      {estimate.rejection_reason && (
        <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-start gap-2">
          <XCircle className="text-red-600 flex-shrink-0 mt-0.5" size={16} />
          <div>
            <div className="text-sm font-medium text-red-800">Rejection Reason</div>
            <div className="text-sm text-red-700">{estimate.rejection_reason}</div>
          </div>
        </div>
      )}

      {/* Line Items Table */}
      <div className="border rounded-lg overflow-hidden mb-4">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase w-10">#</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">Item</th>
              <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase w-20">Qty</th>
              <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase w-28">Price</th>
              <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 uppercase w-28">Total</th>
              <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase w-24">ATP</th>
              <th className="px-3 py-2 w-10"></th>
            </tr>
          </thead>
          <tbody>
            {estimate.line_items.length === 0 ? (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-gray-500">
                  No line items yet. Click "Add Line" to add items.
                </td>
              </tr>
            ) : (
              estimate.line_items.map((item, idx) => (
                <LineItemRow
                  key={item.id}
                  item={item}
                  index={idx}
                  isDraft={isDraft}
                  onDelete={onDeleteLine}
                />
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Add Line Button (Draft only) */}
      {isDraft && (
        <div className="mb-4">
          <button
            onClick={onAddLine}
            className="flex items-center gap-2 text-sm text-quantum-600 hover:text-quantum-700 font-medium"
          >
            <Plus size={16} />
            Add Line
          </button>
        </div>
      )}

      {/* Totals */}
      <div className="border-t pt-4">
        <div className="flex justify-end">
          <div className="w-64 space-y-2">
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Subtotal</span>
              <span className="font-medium">{formatCurrency(estimate.subtotal)}</span>
            </div>
            <div className="flex justify-between text-sm">
              <span className="text-gray-600">Tax</span>
              <span className="font-medium">{formatCurrency(estimate.tax_amount)}</span>
            </div>
            {estimate.margin_percent !== undefined && estimate.margin_percent !== null && (
              <div className="flex justify-between text-sm">
                <span className="text-gray-600">Margin</span>
                <span className="font-medium text-green-600">{estimate.margin_percent.toFixed(1)}%</span>
              </div>
            )}
            <div className="flex justify-between text-lg font-semibold border-t pt-2">
              <span>Total</span>
              <span>{formatCurrency(estimate.total_amount)}</span>
            </div>
          </div>
        </div>
      </div>

      {/* Action Button */}
      <div className="mt-4 flex justify-end">
        <ActionButton status={estimate.status} onAction={onAction} />
      </div>
    </div>
  );
}
