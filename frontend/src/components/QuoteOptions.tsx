import React from 'react';
import { Clock, DollarSign, Zap, Star, Check } from 'lucide-react';
import { QuoteOption } from '../types';

interface QuoteOptionsProps {
  options: {
    fastest: QuoteOption;
    cheapest: QuoteOption;
    balanced: QuoteOption;
  };
  customerName?: string;
  onAccept?: (quoteType: string) => void;
}

function QuoteCard({
  option,
  type,
  onAccept,
}: {
  option: QuoteOption;
  type: 'fastest' | 'cheapest' | 'balanced';
  onAccept?: (type: string) => void;
}) {
  const config = {
    fastest: {
      icon: Zap,
      color: 'orange',
      label: 'Fastest',
      bgColor: 'bg-orange-50',
      borderColor: 'border-l-orange-500',
      textColor: 'text-orange-600',
      buttonColor: 'bg-orange-500 hover:bg-orange-600',
    },
    cheapest: {
      icon: DollarSign,
      color: 'green',
      label: 'Cheapest',
      bgColor: 'bg-green-50',
      borderColor: 'border-l-green-500',
      textColor: 'text-green-600',
      buttonColor: 'bg-green-500 hover:bg-green-600',
    },
    balanced: {
      icon: Star,
      color: 'blue',
      label: 'Recommended',
      bgColor: 'bg-quantum-50',
      borderColor: 'border-l-quantum-500',
      textColor: 'text-quantum-600',
      buttonColor: 'bg-quantum-500 hover:bg-quantum-600',
    },
  };

  const { icon: Icon, label, bgColor, borderColor, textColor, buttonColor } = config[type];

  const formatDate = (dateStr: string) => {
    const date = new Date(dateStr);
    return date.toLocaleDateString('en-US', {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  };

  const formatCurrency = (amount: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USD',
    }).format(amount);
  };

  return (
    <div
      className={`quote-card card border-l-4 ${borderColor} ${bgColor} hover:shadow-lg transition-all cursor-pointer`}
    >
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className={`p-2 rounded-lg ${textColor} bg-white`}>
            <Icon size={20} />
          </div>
          <span className={`font-semibold ${textColor}`}>{label}</span>
        </div>
        {type === 'balanced' && (
          <span className="px-2 py-1 bg-quantum-100 text-quantum-700 text-xs rounded-full font-medium">
            Best Value
          </span>
        )}
      </div>

      <div className="mb-4">
        <div className="text-3xl font-bold text-gray-900">
          {formatCurrency(option.total_price)}
        </div>
        <div className="text-sm text-gray-500 mt-1">
          <Clock size={14} className="inline mr-1" />
          Delivery: {formatDate(option.estimated_delivery_date)}
          <span className="ml-2">({option.lead_time_days} days)</span>
        </div>
      </div>

      <div className="space-y-2 mb-4">
        {option.highlights?.map((highlight, idx) => (
          <div key={idx} className="flex items-center gap-2 text-sm text-gray-600">
            <Check size={14} className={textColor} />
            {highlight}
          </div>
        ))}
      </div>

      <div className="text-xs text-gray-500 mb-4 border-t pt-3">
        <div className="grid grid-cols-3 gap-2">
          <div>
            <div className="font-medium">Materials</div>
            <div>{formatCurrency(option.material_cost)}</div>
          </div>
          <div>
            <div className="font-medium">Labor</div>
            <div>{formatCurrency(option.labor_cost)}</div>
          </div>
          <div>
            <div className="font-medium">Overhead</div>
            <div>{formatCurrency(option.overhead_cost)}</div>
          </div>
        </div>
      </div>

      {onAccept && (
        <button
          onClick={() => onAccept(type)}
          className={`w-full py-2 text-white font-medium rounded-lg ${buttonColor} transition-colors`}
        >
          Accept {label}
        </button>
      )}
    </div>
  );
}

export function QuoteOptions({ options, customerName, onAccept }: QuoteOptionsProps) {
  return (
    <div className="space-y-4">
      {customerName && (
        <div className="text-sm text-gray-500">
          Quote options for <span className="font-medium text-gray-700">{customerName}</span>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <QuoteCard option={options.fastest} type="fastest" onAccept={onAccept} />
        <QuoteCard option={options.balanced} type="balanced" onAccept={onAccept} />
        <QuoteCard option={options.cheapest} type="cheapest" onAccept={onAccept} />
      </div>
    </div>
  );
}
