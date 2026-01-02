# Estimate UI & Chat Integration Design

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add chat intents and frontend components to create, view, and manage estimates through the existing chat interface.

**Architecture:** Hybrid approach - chat handles workflow actions (create, submit, approve, send), UI card handles line item editing (add/delete).

**Tech Stack:** React + TypeScript frontend, LangGraph hub intents, existing EstimateService backend

---

## Chat Intents

| Intent | Example Phrases | Action |
|--------|----------------|--------|
| `CREATE_ESTIMATE` | "Create estimate for Acme", "New quote for Widget Corp" | Creates draft, returns estimate card |
| `LIST_ESTIMATES` | "Show my estimates", "List quotes" | Returns estimate list |
| `VIEW_ESTIMATE` | "Show estimate E-123", "Open E-20260102-0003" | Returns estimate card |
| `SUBMIT_ESTIMATE` | "Submit E-123 for approval" | Triggers workflow, returns updated card |
| `APPROVE_ESTIMATE` | "Approve estimate E-123" | Status → approved |
| `REJECT_ESTIMATE` | "Reject E-123 because pricing too low" | Status → rejected, captures reason |
| `SEND_ESTIMATE` | "Send E-123 to customer" | Status → sent |
| `ACCEPT_ESTIMATE` | "Customer accepted E-123" | Status → accepted |

**Response Types:**
- `estimate_card` - Full estimate with editable line items
- `estimate_list` - Simple list with status badges

---

## UI Components

### EstimateCard

Displays full estimate with:
- Header: Estimate number, version, status badge (color-coded)
- Customer info, valid until date, earliest delivery with ATP warning
- Line items table with columns: #, Item, Qty, Price, Total, ATP status, Delete button
- Add Line button (opens modal)
- Footer: Subtotal, tax, margin, total
- Action button based on status (Submit/Approve/Send/Accept)

Status colors:
- Draft: Yellow
- Pending Approval: Orange
- Approved: Green
- Sent: Blue
- Accepted: Green (check)
- Rejected: Red

Delete button only visible when status = draft.

### AddLineModal

Two modes via toggle:
1. **Select from Inventory**: Searchable dropdown, auto-fills price, shows ATP
2. **Custom Item**: Free-text description, manual price entry

Fields:
- Description (dropdown or text based on mode)
- Quantity
- Unit Price
- Discount % (optional)
- Notes (optional)
- Calculated line total display

### EstimateList

Simple list showing:
- Estimate number
- Customer name
- Total amount
- Status badge

Clicking a row triggers "View estimate E-xxx" action.

---

## Data Flow

### Chat Flow
```
User message → Hub classifies intent → Execute action → Return {type, data, message} → GenerativeUI renders component
```

### UI Actions (Add/Delete Line)
- Buttons call REST API directly (POST/DELETE /api/v1/estimates/{id}/lines)
- On success, refresh estimate data via GET /api/v1/estimates/{id}
- Re-render card with updated data
- No chat round-trip for line edits

---

## Files to Create/Modify

### New Files
- `frontend/src/components/EstimateCard.tsx`
- `frontend/src/components/EstimateList.tsx`
- `frontend/src/components/AddLineModal.tsx`

### Modified Files
- `backend/hub.py` - Add 8 intent handlers and response builders
- `frontend/src/components/GenerativeUI.tsx` - Add estimate_card and estimate_list cases
- `frontend/src/types/index.ts` - Add EstimateData, EstimateLineItem, etc. interfaces

---

## Implementation Tasks

### Task 1: TypeScript Types
Add interfaces for estimate data structures.

### Task 2: EstimateList Component
Simple list component for displaying estimates.

### Task 3: EstimateCard Component
Full estimate display with line items table.

### Task 4: AddLineModal Component
Modal with inventory picker and custom item modes.

### Task 5: GenerativeUI Integration
Add cases for estimate_card and estimate_list types.

### Task 6: Hub Intents
Add all 8 intent handlers to hub.py with proper response formatting.

### Task 7: Seed Data
Ensure test data exists for validation:
- At least 2 customers in database
- At least 5 inventory items with varying stock levels (for ATP testing)
- At least 1 price book with entries (optional, for pricing resolution)

### Task 8: End-to-End Validation
Test complete flows via chat and UI:

**Chat Tests:**
1. "Create an estimate for Acme" → Verify estimate card appears with draft status
2. "Show my estimates" → Verify list shows the new estimate
3. "Show estimate E-xxx" → Verify full estimate card with line items

**UI Tests:**
4. Click "Add Line" → Select inventory item → Verify ATP status and price auto-fill
5. Click "Add Line" → Custom item → Verify manual entry works
6. Click delete (🗑) on a line → Verify line removed and totals update
7. Verify totals recalculate correctly (subtotal, tax, margin)

**Workflow Tests:**
8. "Submit estimate E-xxx" → Verify status changes to approved/pending
9. "Send estimate E-xxx" → Verify status changes to sent
10. "Customer accepted E-xxx" → Verify status changes to accepted

**Edge Cases:**
11. Try to add line to non-draft estimate → Verify error shown
12. Create estimate with partial ATP item → Verify warning displayed
13. View estimate list when empty → Verify graceful empty state
