import React, { useState, useEffect } from 'react';
import { X, Package, FileText, Search, AlertTriangle, CheckCircle } from 'lucide-react';
import { Item, EstimateLineItemCreate, ATPStatus } from '../types';

interface AddLineModalProps {
  isOpen: boolean;
  onClose: () => void;
  onAdd: (lineItem: EstimateLineItemCreate) => void;
  estimateId: number;
}

interface InventoryItem extends Item {
  atp_status?: ATPStatus;
  atp_available?: number;
}

const API_BASE = '/api';

async function searchInventory(query: string): Promise<InventoryItem[]> {
  try {
    const response = await fetch(`${API_BASE}/items?search=${encodeURIComponent(query)}`);
    if (!response.ok) return [];
    return await response.json();
  } catch {
    return [];
  }
}

async function checkATP(itemId: number, quantity: number): Promise<{ status: ATPStatus; available: number }> {
  try {
    const response = await fetch(`${API_BASE}/items/check-stock/${itemId}?quantity=${quantity}`);
    if (!response.ok) return { status: 'available', available: quantity };
    const data = await response.json();
    return {
      status: data.available ? 'available' : data.shortage > 0 ? 'partial' : 'backorder',
      available: data.quantity_on_hand || 0,
    };
  } catch {
    return { status: 'available', available: 0 };
  }
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
}

export function AddLineModal({ isOpen, onClose, onAdd, estimateId }: AddLineModalProps) {
  const [mode, setMode] = useState<'inventory' | 'custom'>('inventory');
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<InventoryItem[]>([]);
  const [selectedItem, setSelectedItem] = useState<InventoryItem | null>(null);
  const [isSearching, setIsSearching] = useState(false);
  const [showDropdown, setShowDropdown] = useState(false);

  // Form fields
  const [description, setDescription] = useState('');
  const [quantity, setQuantity] = useState(1);
  const [unitPrice, setUnitPrice] = useState(0);
  const [discountPct, setDiscountPct] = useState(0);
  const [notes, setNotes] = useState('');

  // ATP status
  const [atpStatus, setAtpStatus] = useState<ATPStatus>('available');
  const [atpAvailable, setAtpAvailable] = useState<number>(0);

  // Calculate line total
  const lineTotal = quantity * unitPrice * (1 - discountPct / 100);

  // Reset form when modal closes
  useEffect(() => {
    if (!isOpen) {
      setMode('inventory');
      setSearchQuery('');
      setSearchResults([]);
      setSelectedItem(null);
      setDescription('');
      setQuantity(1);
      setUnitPrice(0);
      setDiscountPct(0);
      setNotes('');
      setAtpStatus('available');
      setShowDropdown(false);
    }
  }, [isOpen]);

  // Search inventory as user types
  useEffect(() => {
    if (mode !== 'inventory' || searchQuery.length < 2) {
      setSearchResults([]);
      return;
    }

    const timer = setTimeout(async () => {
      setIsSearching(true);
      const results = await searchInventory(searchQuery);
      setSearchResults(results);
      setIsSearching(false);
      setShowDropdown(true);
    }, 300);

    return () => clearTimeout(timer);
  }, [searchQuery, mode]);

  // Check ATP when quantity changes for selected item
  useEffect(() => {
    if (!selectedItem || quantity <= 0) return;

    const checkStock = async () => {
      const result = await checkATP(selectedItem.id, quantity);
      setAtpStatus(result.status);
      setAtpAvailable(result.available);
    };

    checkStock();
  }, [selectedItem, quantity]);

  const handleSelectItem = (item: InventoryItem) => {
    setSelectedItem(item);
    setDescription(item.name);
    setUnitPrice(item.cost_per_unit);
    setSearchQuery(item.name);
    setShowDropdown(false);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();

    if (!description.trim()) return;

    const lineItem: EstimateLineItemCreate = {
      item_id: selectedItem?.id,
      description: description.trim(),
      quantity,
      unit_price: unitPrice,
      discount_pct: discountPct / 100,
      notes: notes.trim() || undefined,
    };

    onAdd(lineItem);
    onClose();
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-xl w-full max-w-lg mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b">
          <h2 className="text-lg font-semibold text-gray-900">Add Line Item</h2>
          <button
            onClick={onClose}
            className="text-gray-400 hover:text-gray-600 transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        {/* Mode Toggle */}
        <div className="px-6 py-4 border-b bg-gray-50">
          <div className="flex gap-2">
            <button
              onClick={() => {
                setMode('inventory');
                setSelectedItem(null);
                setDescription('');
                setUnitPrice(0);
              }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === 'inventory'
                  ? 'bg-quantum-500 text-white'
                  : 'bg-white text-gray-700 border hover:bg-gray-50'
              }`}
            >
              <Package size={16} />
              Select from Inventory
            </button>
            <button
              onClick={() => {
                setMode('custom');
                setSelectedItem(null);
                setSearchQuery('');
                setSearchResults([]);
              }}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                mode === 'custom'
                  ? 'bg-quantum-500 text-white'
                  : 'bg-white text-gray-700 border hover:bg-gray-50'
              }`}
            >
              <FileText size={16} />
              Custom Item
            </button>
          </div>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {/* Description / Item Search */}
          {mode === 'inventory' ? (
            <div className="relative">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Search Inventory
              </label>
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
                <input
                  type="text"
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  onFocus={() => searchResults.length > 0 && setShowDropdown(true)}
                  placeholder="Type to search items..."
                  className="w-full pl-10 pr-4 py-2 border rounded-lg focus:ring-2 focus:ring-quantum-500 focus:border-quantum-500"
                />
                {isSearching && (
                  <span className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-sm">
                    Searching...
                  </span>
                )}
              </div>

              {/* Search Results Dropdown */}
              {showDropdown && searchResults.length > 0 && (
                <div className="absolute z-10 w-full mt-1 bg-white border rounded-lg shadow-lg max-h-48 overflow-y-auto">
                  {searchResults.map((item) => (
                    <button
                      key={item.id}
                      type="button"
                      onClick={() => handleSelectItem(item)}
                      className="w-full px-4 py-2 text-left hover:bg-gray-50 flex items-center justify-between"
                    >
                      <div>
                        <div className="font-medium text-gray-900">{item.name}</div>
                        <div className="text-sm text-gray-500">{item.sku}</div>
                      </div>
                      <div className="text-right">
                        <div className="font-medium">{formatCurrency(item.cost_per_unit)}</div>
                        <div className="text-xs text-gray-500">{item.quantity_on_hand} in stock</div>
                      </div>
                    </button>
                  ))}
                </div>
              )}

              {/* Selected Item Display */}
              {selectedItem && (
                <div className="mt-2 p-3 bg-quantum-50 border border-quantum-200 rounded-lg">
                  <div className="flex items-center justify-between">
                    <div>
                      <div className="font-medium text-quantum-900">{selectedItem.name}</div>
                      <div className="text-sm text-quantum-600">{selectedItem.sku}</div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setSelectedItem(null);
                        setSearchQuery('');
                        setDescription('');
                        setUnitPrice(0);
                      }}
                      className="text-quantum-600 hover:text-quantum-800"
                    >
                      <X size={16} />
                    </button>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Description
              </label>
              <input
                type="text"
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                placeholder="Enter item description"
                required
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-quantum-500 focus:border-quantum-500"
              />
            </div>
          )}

          {/* Quantity and Price Row */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Quantity
              </label>
              <input
                type="number"
                value={quantity}
                onChange={(e) => setQuantity(Math.max(1, parseInt(e.target.value) || 1))}
                min="1"
                step="1"
                required
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-quantum-500 focus:border-quantum-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Unit Price
              </label>
              <input
                type="number"
                value={unitPrice}
                onChange={(e) => setUnitPrice(Math.max(0, parseFloat(e.target.value) || 0))}
                min="0"
                step="0.01"
                required
                className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-quantum-500 focus:border-quantum-500"
              />
            </div>
          </div>

          {/* Discount */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Discount %
            </label>
            <input
              type="number"
              value={discountPct}
              onChange={(e) => setDiscountPct(Math.min(100, Math.max(0, parseFloat(e.target.value) || 0)))}
              min="0"
              max="100"
              step="0.1"
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-quantum-500 focus:border-quantum-500"
            />
          </div>

          {/* Notes */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Notes (optional)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Additional notes for this line item"
              rows={2}
              className="w-full px-4 py-2 border rounded-lg focus:ring-2 focus:ring-quantum-500 focus:border-quantum-500"
            />
          </div>

          {/* ATP Status (for inventory items) */}
          {selectedItem && (
            <div className={`p-3 rounded-lg flex items-center gap-2 ${
              atpStatus === 'available' ? 'bg-green-50 text-green-700' :
              atpStatus === 'partial' ? 'bg-yellow-50 text-yellow-700' :
              'bg-red-50 text-red-700'
            }`}>
              {atpStatus === 'available' ? (
                <CheckCircle size={16} />
              ) : (
                <AlertTriangle size={16} />
              )}
              <span className="text-sm">
                {atpStatus === 'available' && `${atpAvailable} available in stock`}
                {atpStatus === 'partial' && `Only ${atpAvailable} available (${quantity - atpAvailable} on backorder)`}
                {atpStatus === 'backorder' && 'Item is on backorder'}
              </span>
            </div>
          )}

          {/* Line Total */}
          <div className="p-4 bg-gray-50 rounded-lg">
            <div className="flex justify-between items-center">
              <span className="text-gray-600">Line Total</span>
              <span className="text-xl font-semibold text-gray-900">
                {formatCurrency(lineTotal)}
              </span>
            </div>
            {discountPct > 0 && (
              <div className="text-sm text-green-600 text-right mt-1">
                {discountPct}% discount applied
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-3 pt-4">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2 border rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mode === 'inventory' ? !selectedItem : !description.trim()}
              className="flex-1 px-4 py-2 bg-quantum-500 text-white rounded-lg hover:bg-quantum-600 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Add Line
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
