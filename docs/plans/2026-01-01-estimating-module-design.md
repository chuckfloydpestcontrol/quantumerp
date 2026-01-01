# Quantum ERP Estimating Module - Design Document

**Date:** 2026-01-01
**Scope:** Phase 2 (MVP + Intelligent Drafting)
**Status:** Approved for implementation

---

## Executive Summary

This document specifies the Estimating Module for Quantum ERP, implementing a Hybrid Generative UI architecture that combines chat-driven natural language input with structured form editing. The module enables users to create quotes via conversational prompts while refining details through embedded, interactive cards.

### Key Decisions

| Decision | Choice |
|----------|--------|
| Edit Mode | Both inline card editing AND modal expansion |
| Pricing Engine | Full Price Books with customer/tier + volume breaks |
| RAG Integration | Product matching + Customer purchase history |
| ATP Handling | Active warnings that block impossible dates |
| PDF Generation | Server-side (WeasyPrint) |
| Approval Flow | Manager approval with configurable rules |
| Versioning | Snapshot versioning (v1 → v2 on revision) |

---

## 1. Data Model Architecture

### New Tables

#### Estimate (Header)

```sql
CREATE TABLE estimates (
    id SERIAL PRIMARY KEY,
    estimate_number VARCHAR(50) NOT NULL,
    version INT NOT NULL DEFAULT 1,
    parent_estimate_id INT REFERENCES estimates(id),
    superseded_by_id INT REFERENCES estimates(id),

    customer_id INT NOT NULL REFERENCES customers(id),
    status VARCHAR(20) NOT NULL DEFAULT 'draft',
    -- DRAFT, PENDING_APPROVAL, APPROVED, SENT, ACCEPTED, REJECTED, EXPIRED

    currency_code CHAR(3) DEFAULT 'USD',
    exchange_rate DECIMAL(10,6) DEFAULT 1.0,
    price_book_id INT REFERENCES price_books(id),

    valid_until DATE,
    subtotal DECIMAL(12,2) NOT NULL DEFAULT 0,
    tax_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    total_amount DECIMAL(12,2) NOT NULL DEFAULT 0,
    margin_percent DECIMAL(5,4),

    requested_delivery_date DATE,
    earliest_delivery_date DATE,
    delivery_feasible BOOLEAN DEFAULT TRUE,

    pending_approvers JSONB,  -- ["manager", "finance"]
    approved_by INT REFERENCES users(id),
    approved_at TIMESTAMP WITH TIME ZONE,
    rejection_reason TEXT,
    sent_at TIMESTAMP WITH TIME ZONE,
    accepted_at TIMESTAMP WITH TIME ZONE,

    notes TEXT,
    metadata JSONB,  -- AI context, extraction confidence

    created_by INT REFERENCES users(id),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(estimate_number, version)
);
```

#### EstimateLineItem

```sql
CREATE TABLE estimate_line_items (
    id SERIAL PRIMARY KEY,
    estimate_id INT NOT NULL REFERENCES estimates(id) ON DELETE CASCADE,

    item_id INT REFERENCES items(id),
    description TEXT NOT NULL,

    quantity DECIMAL(12,4) NOT NULL,
    unit_price DECIMAL(12,4) NOT NULL,
    list_price DECIMAL(12,4),  -- Original price before discount
    unit_cost DECIMAL(12,4),   -- Internal cost (hidden from customer)
    discount_pct DECIMAL(5,4) DEFAULT 0,
    line_total DECIMAL(12,2) NOT NULL,

    tax_code_id INT REFERENCES tax_codes(id),
    tax_amount DECIMAL(12,2) DEFAULT 0,

    -- ATP (Available to Promise) fields
    atp_status VARCHAR(20) DEFAULT 'available',  -- available, partial, backorder
    atp_available_qty DECIMAL(12,4),
    atp_shortage_qty DECIMAL(12,4),
    atp_lead_time_days INT,

    sort_order INT NOT NULL DEFAULT 0,
    notes TEXT,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### PriceBook

```sql
CREATE TABLE price_books (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    is_default BOOLEAN DEFAULT FALSE,

    customer_id INT REFERENCES customers(id),  -- NULL = applies to all
    customer_segment VARCHAR(50),  -- 'wholesale', 'retail', etc.

    currency_code CHAR(3) DEFAULT 'USD',
    valid_from DATE,
    valid_until DATE,
    active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

#### PriceBookEntry

```sql
CREATE TABLE price_book_entries (
    id SERIAL PRIMARY KEY,
    price_book_id INT NOT NULL REFERENCES price_books(id) ON DELETE CASCADE,
    item_id INT NOT NULL REFERENCES items(id),

    min_qty DECIMAL(12,4) DEFAULT 1,  -- Tiered pricing
    max_qty DECIMAL(12,4),            -- NULL = unlimited
    unit_price DECIMAL(12,4) NOT NULL,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),

    UNIQUE(price_book_id, item_id, min_qty)
);
```

#### ApprovalRule

```sql
CREATE TABLE approval_rules (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,

    condition_type VARCHAR(50) NOT NULL,
    -- margin_below, total_above, payment_terms_above, customer_new
    threshold_value DECIMAL(12,4),

    approver_role VARCHAR(50) NOT NULL,  -- manager, finance, vp
    priority INT DEFAULT 0,  -- For ordering multiple rules
    active BOOLEAN DEFAULT TRUE,

    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
```

### Entity Relationships

```
Customer (1) ──────< (many) Estimate
    │                        │
    │                        └──< (many) EstimateLineItem ───> (1) Item
    │                        │
    └──< (many) PriceBook ──< (many) PriceBookEntry ───> (1) Item

Estimate (parent) ──< (many) Estimate (versions)
```

---

## 2. API Design

### Estimate Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/estimates/generate` | Create from natural language |
| GET | `/api/v1/estimates` | List estimates with filters |
| GET | `/api/v1/estimates/{id}` | Get full estimate with lines |
| PATCH | `/api/v1/estimates/{id}` | Update header fields |
| DELETE | `/api/v1/estimates/{id}` | Delete draft estimate |
| POST | `/api/v1/estimates/{id}/lines` | Add line item |
| PATCH | `/api/v1/estimates/{id}/lines/{line_id}` | Update line item |
| DELETE | `/api/v1/estimates/{id}/lines/{line_id}` | Remove line item |
| POST | `/api/v1/estimates/{id}/actions/submit` | Submit for approval |
| POST | `/api/v1/estimates/{id}/actions/approve` | Approve estimate |
| POST | `/api/v1/estimates/{id}/actions/reject` | Reject with reason |
| POST | `/api/v1/estimates/{id}/actions/send` | Send to customer |
| POST | `/api/v1/estimates/{id}/actions/accept` | Accept and create job |
| POST | `/api/v1/estimates/{id}/actions/revise` | Create new version |
| GET | `/api/v1/estimates/{id}/pdf` | Generate PDF |
| GET | `/api/v1/estimates/{id}/versions` | Get version history |

### Price Book Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/price-books` | List price books |
| POST | `/api/v1/price-books` | Create price book |
| GET | `/api/v1/price-books/{id}` | Get price book |
| PATCH | `/api/v1/price-books/{id}` | Update price book |
| GET | `/api/v1/price-books/{id}/entries` | List entries |
| POST | `/api/v1/price-books/{id}/entries` | Add entry |
| PATCH | `/api/v1/price-books/{id}/entries/{entry_id}` | Update entry |
| DELETE | `/api/v1/price-books/{id}/entries/{entry_id}` | Remove entry |

### Approval Rule Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/v1/approval-rules` | List rules |
| POST | `/api/v1/approval-rules` | Create rule |
| PATCH | `/api/v1/approval-rules/{id}` | Update rule |
| DELETE | `/api/v1/approval-rules/{id}` | Delete rule |

### Pricing Resolution Logic

```python
async def resolve_price(item_id: int, customer_id: int, quantity: Decimal) -> Decimal:
    """
    Price resolution hierarchy:
    1. Customer-specific price book
    2. Customer segment price book
    3. Default price book

    Within each book, apply volume tier based on quantity.
    """
    # 1. Check customer-specific price book
    customer_book = await get_price_book(customer_id=customer_id)
    if customer_book:
        price = await get_tiered_price(customer_book.id, item_id, quantity)
        if price:
            return price

    # 2. Check segment price book
    customer = await get_customer(customer_id)
    if customer.segment:
        segment_book = await get_price_book(segment=customer.segment)
        if segment_book:
            price = await get_tiered_price(segment_book.id, item_id, quantity)
            if price:
                return price

    # 3. Fall back to default
    default_book = await get_default_price_book()
    price = await get_tiered_price(default_book.id, item_id, quantity)
    if price:
        return price

    # 4. Last resort: item's cost_per_unit
    item = await get_item(item_id)
    return item.cost_per_unit
```

---

## 3. NLP Pipeline & RAG Integration

### Pipeline Steps

```
User Input
    │
    ▼
┌─────────────────────────────────────┐
│ 1. Entity Extraction (LLM)          │
│    - customer_name                  │
│    - requested_date                 │
│    - line_items[{desc, qty}]        │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 2. Customer Resolution              │
│    - Fuzzy match on customers table │
│    - Load price book, preferences   │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 3. Product Resolution (RAG)         │
│    - pgvector semantic search       │
│    - Customer history lookup        │
│    - Confidence scoring             │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 4. Pricing + ATP Check              │
│    - Resolve prices from book       │
│    - Check inventory levels         │
│    - Calculate lead times           │
│    - Validate delivery feasibility  │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│ 5. Draft Estimate Creation          │
│    - Create Estimate record         │
│    - Create EstimateLineItems       │
│    - Return card JSON               │
└─────────────────────────────────────┘
```

### Confidence Thresholds

| Score | Action |
|-------|--------|
| >= 0.85 | Auto-resolve, no confirmation needed |
| 0.70 - 0.84 | Yellow highlight, suggest confirmation |
| < 0.70 | Require user selection from options |

### Customer History Query

```python
async def get_customer_product_history(customer_id: int, item_description: str) -> list[dict]:
    """
    Find products this customer has ordered that match the description.
    Used to disambiguate "bolts" → "M5-SS-100" based on past orders.
    """
    # Get customer's past estimate line items
    past_items = await db.execute(
        select(EstimateLineItem, Item)
        .join(Estimate)
        .join(Item)
        .where(Estimate.customer_id == customer_id)
        .where(Estimate.status == 'accepted')
        .order_by(Estimate.accepted_at.desc())
        .limit(100)
    )

    # Score by semantic similarity to description
    description_embedding = await get_embedding(item_description)
    scored = []
    for line, item in past_items:
        similarity = cosine_similarity(description_embedding, item.embedding)
        scored.append({
            "item_id": item.id,
            "item_name": item.name,
            "sku": item.sku,
            "similarity": similarity,
            "times_ordered": await count_orders(customer_id, item.id)
        })

    return sorted(scored, key=lambda x: (x["similarity"], x["times_ordered"]), reverse=True)
```

---

## 4. Frontend UI Components

### Component Structure

```
src/components/estimates/
├── EstimateCard.tsx          # Main card in chat stream
├── EstimateLineTable.tsx     # Inline line item display
├── EstimateEditModal.tsx     # Full modal for complex edits
├── LineItemRow.tsx           # Editable row with ATP indicators
├── ProductSearch.tsx         # Typeahead for adding items
├── ATPWarning.tsx            # Stock/delivery warning display
├── ApprovalActions.tsx       # Approve/Reject buttons
├── VersionHistory.tsx        # Version comparison view
└── EstimatePDFPreview.tsx    # PDF preview before sending
```

### EstimateCard Layout

```
┌─────────────────────────────────────────────────────────────────┐
│ ESTIMATE E-20260101-0001 v1                    [DRAFT ▼]        │
│ Customer: Acme Corp                                             │
├─────────────────────────────────────────────────────────────────┤
│ Item                    Qty    Unit Price    Total              │
│ ─────────────────────────────────────────────────────           │
│ Aluminum Bracket       [50]    $12.00        $600.00            │
│   └─ ⚠️ 5 units backordered (+7 days)                           │
│ M5 Stainless Bolts    [100]    $0.25         $25.00             │
│   └─ ✅ In stock                                                │
├─────────────────────────────────────────────────────────────────┤
│ Subtotal: $625.00   Tax: $50.00   Total: $675.00                │
│ Margin: 32%                                                     │
│ ─────────────────────────────────────────────────────           │
│ ⚠️ Requested date Jan 15 cannot be met. Earliest: Jan 22        │
├─────────────────────────────────────────────────────────────────┤
│ [+ Add Line]    [Edit Details]    [Submit for Approval]         │
└─────────────────────────────────────────────────────────────────┘
```

### Inline Editing Behavior

- Quantity field: Click to edit, blur to save
- On change: PATCH `/api/v1/estimates/{id}/lines/{line_id}`
- Response triggers: price recalc, ATP recheck, card re-render

### Modal Editing Features

- Full spreadsheet-style grid
- Drag-to-reorder rows
- Bulk discount application
- Notes per line item
- Delivery date picker with live ATP validation

---

## 5. Approval Workflow

### State Transitions

```
DRAFT ─────────────────────────────────────────────────┐
  │                                                     │
  │ submit()                                            │
  ▼                                                     │
[Check Approval Rules]                                  │
  │                                                     │
  ├─ rules triggered ──▶ PENDING_APPROVAL               │
  │                           │                         │
  │                           ├─ approve() ──▶ APPROVED │
  │                           │                    │    │
  │                           └─ reject() ──▶ REJECTED  │
  │                                              │      │
  │                                              │ revise()
  └─ no rules ──────────▶ APPROVED               └──────┘
                              │
                              │ send()
                              ▼
                            SENT
                              │
              ┌───────────────┼───────────────┐
              │               │               │
              ▼               ▼               ▼
          ACCEPTED        REJECTED        EXPIRED
              │
              │ (auto)
              ▼
         JOB CREATED
```

### Approval Rules

| Rule Name | Condition | Threshold | Approver |
|-----------|-----------|-----------|----------|
| Low Margin | margin_percent < | 0.15 | manager |
| High Value | total_amount > | 50000 | manager |
| Extended Terms | payment_terms > | 60 days | finance |
| New Customer | customer.created_at < | 30 days ago | manager |

### Approval Notification Card

```
┌─────────────────────────────────────────────────────────────────┐
│ 🔔 APPROVAL REQUIRED                                            │
│                                                                 │
│ Estimate E-20260101-0001 for Acme Corp needs your approval.     │
│ Total: $52,400.00 | Margin: 12%                                 │
│                                                                 │
│ Triggered rules:                                                │
│ • High Value (>$50,000)                                         │
│ • Low Margin (<15%)                                             │
│                                                                 │
│ [View Details]    [✓ Approve]    [✗ Reject]                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## 6. Versioning

### Snapshot Creation

When revising a SENT or REJECTED estimate:

```python
async def revise_estimate(estimate_id: int) -> Estimate:
    original = await get_estimate(estimate_id)

    # Create new version
    new_estimate = Estimate(
        estimate_number=original.estimate_number,
        version=original.version + 1,
        parent_estimate_id=original.id,
        status=EstimateStatus.DRAFT,
        customer_id=original.customer_id,
        price_book_id=original.price_book_id,
        valid_until=original.valid_until,
        requested_delivery_date=original.requested_delivery_date,
        notes=original.notes,
    )
    db.add(new_estimate)
    await db.flush()

    # Clone line items
    for line in original.line_items:
        new_line = EstimateLineItem(
            estimate_id=new_estimate.id,
            item_id=line.item_id,
            description=line.description,
            quantity=line.quantity,
            unit_price=line.unit_price,
            # ... all fields
        )
        db.add(new_line)

    # Mark original as superseded
    original.superseded_by_id = new_estimate.id

    await db.commit()
    return new_estimate
```

### Version History Response

```json
{
  "estimate_number": "E-20260101-0001",
  "versions": [
    {
      "version": 3,
      "status": "draft",
      "created_at": "2026-01-03T10:00:00Z",
      "changes": ["quantity 50→75", "added shipping line"]
    },
    {
      "version": 2,
      "status": "rejected",
      "created_at": "2026-01-02T14:00:00Z",
      "rejection_reason": "Price too high per customer"
    },
    {
      "version": 1,
      "status": "sent",
      "created_at": "2026-01-01T09:00:00Z",
      "changes": null
    }
  ]
}
```

---

## 7. PDF Generation

### Technology

- **Library:** WeasyPrint (HTML/CSS → PDF)
- **Templates:** Jinja2

### Template Structure

```
backend/templates/
├── estimate_pdf.html
├── estimate_pdf.css
└── partials/
    ├── header.html
    ├── line_items.html
    └── footer.html
```

### PDF Sections

1. **Header:** Company logo, estimate number, version, date, validity
2. **Customer Info:** Name, address, contact
3. **Line Items:** Table with item, qty, price, totals
4. **Totals:** Subtotal, tax, grand total
5. **Terms:** Payment terms, validity period, disclaimers
6. **Footer:** Page numbers, generated timestamp

---

## 8. LangGraph Hub Integration

### New Intents

```python
ESTIMATE_INTENTS = """
**Estimating:**
- CREATE_ESTIMATE: Create a new estimate ("Quote for Acme, 50 brackets")
- EDIT_ESTIMATE: Modify estimate ("change quantity to 75", "add shipping")
- SUBMIT_ESTIMATE: Submit for approval ("submit this estimate")
- APPROVE_ESTIMATE: Manager approves ("approve estimate E-20260101-0001")
- REJECT_ESTIMATE: Manager rejects ("reject estimate, price too high")
- SEND_ESTIMATE: Send to customer ("send this quote to customer")
- ACCEPT_ESTIMATE: Customer accepts ("customer accepted the quote")
- VIEW_ESTIMATE: View details ("show estimate E-20260101-0001")
- LIST_ESTIMATES: List estimates ("show pending estimates", "quotes for Acme")
- COMPARE_VERSIONS: Compare versions ("compare v1 and v2")
"""
```

### New State Fields

```python
class AgentState(TypedDict):
    # ... existing fields ...

    # Estimate context
    active_estimate_id: Optional[int]
    extracted_items: Optional[list[dict]]
    ambiguous_products: Optional[list[dict]]
    estimate_action: Optional[str]  # submit, approve, reject, send
```

### New Nodes

```python
workflow.add_node("create_estimate", self._create_estimate_node)
workflow.add_node("edit_estimate", self._edit_estimate_node)
workflow.add_node("submit_estimate", self._submit_estimate_node)
workflow.add_node("approve_estimate", self._approve_estimate_node)
workflow.add_node("reject_estimate", self._reject_estimate_node)
workflow.add_node("send_estimate", self._send_estimate_node)
workflow.add_node("accept_estimate", self._accept_estimate_node)
workflow.add_node("list_estimates", self._list_estimates_node)
workflow.add_node("view_estimate", self._view_estimate_node)
```

---

## 9. Implementation Order

### Layer 1: Database Foundation
- [ ] Alembic migration for new tables
- [ ] SQLAlchemy models (Estimate, EstimateLineItem, PriceBook, etc.)
- [ ] Pydantic schemas

### Layer 2: Core Services
- [ ] EstimateService (CRUD, versioning, status transitions)
- [ ] PricingService (price book resolution, tiered pricing)
- [ ] ATPService (stock checks, lead time calculations)
- [ ] PDFService (WeasyPrint rendering)

### Layer 3: API Endpoints
- [ ] Estimate CRUD routes
- [ ] Action routes (submit, approve, send, accept)
- [ ] Price book management routes
- [ ] PDF generation endpoint

### Layer 4: NLP Pipeline
- [ ] Entity extraction prompts
- [ ] Product resolution with pgvector
- [ ] Customer history lookups
- [ ] Confidence scoring

### Layer 5: Hub Integration
- [ ] New intents in supervisor prompt
- [ ] Estimate-related nodes
- [ ] Thread context management

### Layer 6: Frontend Components
- [ ] EstimateCard with inline editing
- [ ] EstimateEditModal
- [ ] ATP warning displays
- [ ] Approval notification cards

### Layer 7: Polish
- [ ] PDF template styling
- [ ] Email integration
- [ ] Version comparison view

---

## Appendix: Response Type for Generative UI

```python
class UIResponseType(str, Enum):
    # ... existing types ...
    ESTIMATE_CARD = "estimate_card"
    ESTIMATE_LIST = "estimate_list"
    APPROVAL_REQUEST = "approval_request"
    PRODUCT_DISAMBIGUATION = "product_disambiguation"
    ATP_WARNING = "atp_warning"
```
