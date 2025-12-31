import React from 'react';
import {
  FileText,
  Clock,
  AlertTriangle,
  CheckCircle,
  Package,
  XCircle,
  Pause,
} from 'lucide-react';
import { Job, JobStatus as JobStatusType } from '../types';

interface JobStatusProps {
  jobs: Partial<Job>[];
  onJobClick?: (jobNumber: string) => void;
}

const statusConfig: Record<
  string,
  { icon: React.ComponentType<{ size?: number }>; color: string; bg: string; label: string }
> = {
  draft: {
    icon: FileText,
    color: 'text-gray-600',
    bg: 'bg-gray-100',
    label: 'Draft',
  },
  quoted: {
    icon: Clock,
    color: 'text-blue-600',
    bg: 'bg-blue-100',
    label: 'Quoted',
  },
  scheduled: {
    icon: Clock,
    color: 'text-purple-600',
    bg: 'bg-purple-100',
    label: 'Scheduled',
  },
  financial_hold: {
    icon: Pause,
    color: 'text-yellow-600',
    bg: 'bg-yellow-100',
    label: 'Financial Hold',
  },
  in_production: {
    icon: Package,
    color: 'text-orange-600',
    bg: 'bg-orange-100',
    label: 'In Production',
  },
  completed: {
    icon: CheckCircle,
    color: 'text-green-600',
    bg: 'bg-green-100',
    label: 'Completed',
  },
  cancelled: {
    icon: XCircle,
    color: 'text-red-600',
    bg: 'bg-red-100',
    label: 'Cancelled',
  },
};

function StatusBadge({ status }: { status: string }) {
  const config = statusConfig[status] || statusConfig.draft;
  const Icon = config.icon;

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-1 rounded-full text-xs font-medium ${config.bg} ${config.color}`}
    >
      <Icon size={12} />
      {config.label}
    </span>
  );
}

export function JobStatusComponent({ jobs, onJobClick }: JobStatusProps) {
  if (!jobs || jobs.length === 0) {
    return (
      <div className="card text-center py-8">
        <FileText className="mx-auto text-gray-400 mb-2" size={32} />
        <p className="text-gray-500">No jobs found</p>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {jobs.map((job, idx) => (
        <div
          key={job.job_number || idx}
          className="card hover:shadow-md transition-shadow cursor-pointer"
          onClick={() => onJobClick?.(job.job_number || '')}
        >
          <div className="flex items-center justify-between">
            <div>
              <div className="flex items-center gap-2">
                <span className="font-mono font-medium text-gray-900">
                  {job.job_number}
                </span>
                <StatusBadge status={job.status || 'draft'} />
                {job.financial_hold && (
                  <span className="inline-flex items-center gap-1 px-2 py-1 bg-yellow-50 text-yellow-700 rounded-full text-xs">
                    <AlertTriangle size={12} />
                    Hold
                  </span>
                )}
              </div>
              <div className="text-sm text-gray-600 mt-1">{job.customer}</div>
            </div>
            <div className="text-right text-sm text-gray-500">
              {job.created_at &&
                new Date(job.created_at).toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                })}
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}
