import React from 'react';
import { Calendar, Clock } from 'lucide-react';
import { ScheduleData } from '../types';

interface ScheduleViewProps {
  schedules: ScheduleData;
}

export function ScheduleView({ schedules }: ScheduleViewProps) {
  if (!schedules || Object.keys(schedules).length === 0) {
    return (
      <div className="card text-center py-8">
        <Calendar className="mx-auto text-gray-400 mb-2" size={32} />
        <p className="text-gray-500">No schedule data available</p>
      </div>
    );
  }

  const formatTime = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    });
  };

  const getSlotColor = (status: string) => {
    switch (status) {
      case 'reserved':
        return 'bg-blue-100 border-blue-300 text-blue-800';
      case 'in_progress':
        return 'bg-orange-100 border-orange-300 text-orange-800';
      case 'completed':
        return 'bg-green-100 border-green-300 text-green-800';
      default:
        return 'bg-gray-100 border-gray-300 text-gray-800';
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2 text-sm text-gray-600 mb-4">
        <Calendar size={16} />
        <span>Production Schedule</span>
      </div>

      {Object.entries(schedules).map(([machineName, machineData]) => (
        <div key={machineName} className="card">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-medium text-gray-900">{machineName}</h3>
            <span className="text-sm text-gray-500">
              ${machineData.hourly_rate}/hr
            </span>
          </div>

          {machineData.slots.length === 0 ? (
            <div className="text-sm text-gray-400 italic">No scheduled slots</div>
          ) : (
            <div className="space-y-2">
              {machineData.slots.map((slot) => (
                <div
                  key={slot.id}
                  className={`p-3 rounded-lg border ${getSlotColor(slot.status)}`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <Clock size={14} />
                      <span className="text-sm font-medium">
                        {formatTime(slot.start)} - {formatTime(slot.end)}
                      </span>
                    </div>
                    <span className="text-xs uppercase font-medium">
                      {slot.status.replace('_', ' ')}
                    </span>
                  </div>
                  {slot.job_id && (
                    <div className="text-xs mt-1 opacity-75">
                      Job #{slot.job_id}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      ))}
    </div>
  );
}
