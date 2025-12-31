import React, { useState, useEffect } from 'react';
import {
  LayoutDashboard,
  FileText,
  Package,
  Calendar,
  Settings,
  Plus,
  RefreshCw,
  AlertTriangle,
} from 'lucide-react';
import { jobsApi } from '../services/api';

interface SidebarProps {
  onNewChat: () => void;
  onQuickAction: (action: string) => void;
}

export function Sidebar({ onNewChat, onQuickAction }: SidebarProps) {
  const [recentJobs, setRecentJobs] = useState<Array<{
    job_number: string;
    customer_name: string;
    status: string;
    financial_hold: boolean;
  }>>([]);
  const [isLoading, setIsLoading] = useState(false);

  const loadRecentJobs = async () => {
    setIsLoading(true);
    const { data } = await jobsApi.list();
    if (data) {
      setRecentJobs(data.slice(0, 5) as any);
    }
    setIsLoading(false);
  };

  useEffect(() => {
    loadRecentJobs();
  }, []);

  const navItems = [
    { icon: LayoutDashboard, label: 'Dashboard', action: 'show dashboard' },
    { icon: FileText, label: 'Jobs', action: 'show all jobs' },
    { icon: Package, label: 'Inventory', action: 'show inventory' },
    { icon: Calendar, label: 'Schedule', action: 'show schedule' },
  ];

  return (
    <div className="w-64 bg-gray-900 text-white flex flex-col h-full">
      {/* Logo */}
      <div className="p-4 border-b border-gray-800">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-quantum-500 rounded-lg flex items-center justify-center">
            <span className="font-bold text-sm">Q</span>
          </div>
          <div>
            <div className="font-semibold">Quantum HUB</div>
            <div className="text-xs text-gray-400">ERP System</div>
          </div>
        </div>
      </div>

      {/* New Chat Button */}
      <div className="p-4">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 px-4 py-2 bg-quantum-600 hover:bg-quantum-700 rounded-lg transition-colors"
        >
          <Plus size={18} />
          <span>New Chat</span>
        </button>
      </div>

      {/* Navigation */}
      <nav className="px-2">
        {navItems.map((item) => (
          <button
            key={item.label}
            onClick={() => onQuickAction(item.action)}
            className="w-full flex items-center gap-3 px-3 py-2 text-gray-300 hover:text-white hover:bg-gray-800 rounded-lg transition-colors text-left"
          >
            <item.icon size={18} />
            <span className="text-sm">{item.label}</span>
          </button>
        ))}
      </nav>

      {/* Recent Jobs */}
      <div className="flex-1 px-4 py-4 overflow-y-auto">
        <div className="flex items-center justify-between mb-3">
          <span className="text-xs text-gray-400 uppercase font-medium">
            Recent Jobs
          </span>
          <button
            onClick={loadRecentJobs}
            disabled={isLoading}
            className="p-1 text-gray-400 hover:text-white transition-colors"
          >
            <RefreshCw size={14} className={isLoading ? 'animate-spin' : ''} />
          </button>
        </div>

        <div className="space-y-2">
          {recentJobs.length === 0 ? (
            <div className="text-xs text-gray-500 text-center py-4">
              No recent jobs
            </div>
          ) : (
            recentJobs.map((job) => (
              <button
                key={job.job_number}
                onClick={() => onQuickAction(`status of job ${job.job_number}`)}
                className="w-full text-left p-2 bg-gray-800 hover:bg-gray-700 rounded-lg transition-colors"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono text-quantum-400">
                    {job.job_number}
                  </span>
                  {job.financial_hold && (
                    <AlertTriangle size={12} className="text-yellow-500" />
                  )}
                </div>
                <div className="text-xs text-gray-400 truncate mt-1">
                  {job.customer_name}
                </div>
              </button>
            ))
          )}
        </div>
      </div>

      {/* Settings */}
      <div className="p-4 border-t border-gray-800">
        <button className="w-full flex items-center gap-3 px-3 py-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors">
          <Settings size={18} />
          <span className="text-sm">Settings</span>
        </button>
      </div>
    </div>
  );
}
