import React from 'react';
import { FileText, ChevronRight } from 'lucide-react';
import { EstimateListItem, EstimateStatus } from '../types';

interface EstimateListProps {
  estimates: EstimateListItem[];
  onEstimateClick?: (estimateNumber: string) => void;
}

const STATUS_CONFIG: Record<EstimateStatus, { color: string; bg: string; label: string }> = {
  draft: { color: 'text-yellow-700', bg: 'bg-yellow-100', label: 'Draft' },
  pending_approval: { color: 'text-orange-700', bg: 'bg-orange-100', label: 'Pending' },
  approved: { color: 'text-green-700', bg: 'bg-green-100', label: 'Approved' },
  sent: { color: 'text-blue-700', bg: 'bg-blue-100', label: 'Sent' },
  accepted: { color: 'text-green-700', bg: 'bg-green-100', label: 'Accepted' },
  rejected: { color: 'text-red-700', bg: 'bg-red-100', label: 'Rejected' },
  expired: { color: 'text-gray-700', bg: 'bg-gray-100', label: 'Expired' },
};

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

function formatDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
}

function StatusBadge({ status }: { status: EstimateStatus }) {
  const config = STATUS_CONFIG[status] || STATUS_CONFIG.draft;
  return (
    <span className={`px-2 py-1 text-xs font-medium rounded-full ${config.bg} ${config.color}`}>
      {config.label}
    </span>
  );
}

export function EstimateList({ estimates, onEstimateClick }: EstimateListProps) {
  if (!estimates || estimates.length === 0) {
    return (
      <div className="card text-center py-8">
        <FileText className="mx-auto text-gray-400 mb-3" size={32} />
        <p className="text-gray-500">No estimates found</p>
        <p className="text-sm text-gray-400 mt-1">
          Create an estimate by saying "Create estimate for [customer name]"
        </p>
      </div>
    );
  }

  return (
    <div className="card overflow-hidden p-0">
      <div className="divide-y divide-gray-100">
        {estimates.map((estimate) => (
          <div
            key={estimate.id}
            onClick={() => onEstimateClick?.(estimate.estimate_number)}
            className="flex items-center justify-between px-4 py-3 hover:bg-gray-50 cursor-pointer transition-colors"
          >
            <div className="flex items-center gap-3 min-w-0">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-lg bg-quantum-50 flex items-center justify-center">
                  <FileText className="text-quantum-600" size={18} />
                </div>
              </div>
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-sm font-medium text-gray-900">
                    {estimate.estimate_number}
                  </span>
                  {estimate.version > 1 && (
                    <span className="text-xs text-gray-500">v{estimate.version}</span>
                  )}
                </div>
                <div className="text-sm text-gray-500 truncate">
                  {estimate.customer_name || `Customer #${estimate.customer_id}`}
                </div>
              </div>
            </div>

            <div className="flex items-center gap-4">
              <div className="text-right">
                <div className="font-medium text-gray-900">
                  {formatCurrency(estimate.total_amount)}
                </div>
                <div className="text-xs text-gray-500">
                  {formatDate(estimate.created_at)}
                </div>
              </div>
              <StatusBadge status={estimate.status} />
              <ChevronRight className="text-gray-400" size={16} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
