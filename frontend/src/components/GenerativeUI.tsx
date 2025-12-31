import React from 'react';
import { AlertCircle, CheckCircle, Info } from 'lucide-react';
import { UIResponseType, QuoteOptionsData, ScheduleData } from '../types';
import { QuoteOptions } from './QuoteOptions';
import { JobStatusComponent } from './JobStatus';
import { ScheduleView } from './ScheduleView';

interface GenerativeUIProps {
  type: UIResponseType;
  data?: Record<string, unknown>;
  onAction?: (action: string, payload?: unknown) => void;
}

export function GenerativeUI({ type, data, onAction }: GenerativeUIProps) {
  switch (type) {
    case 'quote_options':
      const quoteData = data as unknown as QuoteOptionsData;
      if (quoteData?.options) {
        return (
          <QuoteOptions
            options={quoteData.options}
            customerName={quoteData.customer_name}
            onAccept={(quoteType) => onAction?.('accept_quote', { quoteType })}
          />
        );
      }
      return null;

    case 'job_status':
      const jobData = data as { jobs?: Array<Record<string, unknown>>; message?: string };
      return (
        <div className="space-y-3">
          {jobData?.message && (
            <div className="text-sm text-gray-600">{jobData.message}</div>
          )}
          <JobStatusComponent
            jobs={(jobData?.jobs || []) as any}
            onJobClick={(jobNumber) => onAction?.('view_job', { jobNumber })}
          />
        </div>
      );

    case 'schedule_view':
      const scheduleData = data as { schedules?: ScheduleData; message?: string };
      return (
        <div className="space-y-3">
          {scheduleData?.message && (
            <div className="text-sm text-gray-600">{scheduleData.message}</div>
          )}
          <ScheduleView schedules={scheduleData?.schedules || {}} />
        </div>
      );

    case 'confirmation':
      const confirmData = data as { message?: string; job_number?: string; job_id?: number };
      return (
        <div className="card bg-green-50 border-green-200">
          <div className="flex items-start gap-3">
            <CheckCircle className="text-green-600 flex-shrink-0 mt-0.5" size={20} />
            <div>
              <div className="font-medium text-green-800">Success</div>
              <div className="text-sm text-green-700 mt-1">
                {confirmData?.message || 'Operation completed successfully'}
              </div>
              {confirmData?.job_number && (
                <div className="mt-2">
                  <span className="inline-flex items-center px-2 py-1 bg-green-100 text-green-800 rounded text-sm font-mono">
                    {confirmData.job_number}
                  </span>
                </div>
              )}
            </div>
          </div>
        </div>
      );

    case 'error':
      const errorData = data as { error?: string };
      return (
        <div className="card bg-red-50 border-red-200">
          <div className="flex items-start gap-3">
            <AlertCircle className="text-red-600 flex-shrink-0 mt-0.5" size={20} />
            <div>
              <div className="font-medium text-red-800">Error</div>
              <div className="text-sm text-red-700 mt-1">
                {errorData?.error || 'An error occurred'}
              </div>
            </div>
          </div>
        </div>
      );

    case 'inventory_table':
      const inventoryData = data as { items?: Array<Record<string, unknown>> };
      if (inventoryData?.items?.length) {
        return (
          <div className="card overflow-hidden">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                    Item
                  </th>
                  <th className="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                    SKU
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">
                    Qty
                  </th>
                  <th className="px-4 py-2 text-right text-xs font-medium text-gray-500 uppercase">
                    Status
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {inventoryData.items.map((item, idx) => (
                  <tr key={idx}>
                    <td className="px-4 py-2 text-sm">{item.name as string}</td>
                    <td className="px-4 py-2 text-sm font-mono text-gray-500">
                      {item.sku as string}
                    </td>
                    <td className="px-4 py-2 text-sm text-right">
                      {item.quantity_on_hand as number}
                    </td>
                    <td className="px-4 py-2 text-right">
                      {(item.quantity_on_hand as number) < (item.reorder_point as number) ? (
                        <span className="text-xs text-red-600 bg-red-50 px-2 py-1 rounded">
                          Low Stock
                        </span>
                      ) : (
                        <span className="text-xs text-green-600 bg-green-50 px-2 py-1 rounded">
                          In Stock
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        );
      }
      return null;

    case 'text':
    default:
      return null;
  }
}
