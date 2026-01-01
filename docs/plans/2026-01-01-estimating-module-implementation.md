# Estimating Module Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a comprehensive estimating module with NLP-driven quote creation, price books, ATP warnings, approval workflows, and PDF generation.

**Architecture:** Hybrid Generative UI pattern - chat initiates quotes via NLP, structured cards enable editing. Backend services handle pricing resolution, ATP checks, and approval routing. Snapshot versioning preserves negotiation history.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy 2.0, Alembic, Pydantic V2, LangGraph, WeasyPrint, React 18, TypeScript, Tailwind CSS

---

## Phase 1: Database Foundation

### Task 1.1: Create Alembic Migration for Estimate Tables

**Files:**
- Create: `backend/alembic/versions/004_add_estimating_module.py`

**Step 1: Generate migration file**

Run:
```bash
cd backend && alembic revision -m "add_estimating_module"
```

**Step 2: Write migration**

```python
"""add_estimating_module

Revision ID: 004
Revises: 003_add_uom_to_items
Create Date: 2026-01-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = '004'
down_revision = '003_add_uom_to_items'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # EstimateStatus enum
    op.execute("""
        CREATE TYPE estimate_status AS ENUM (
            'draft', 'pending_approval', 'approved', 'sent',
            'accepted', 'rejected', 'expired'
        )
    """)

    # ATP Status enum
    op.execute("""
        CREATE TYPE atp_status AS ENUM ('available', 'partial', 'backorder')
    """)

    # Price Books table
    op.create_table(
        'price_books',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('is_default', sa.Boolean(), default=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=True),
        sa.Column('customer_segment', sa.String(50), nullable=True),
        sa.Column('currency_code', sa.String(3), default='USD'),
        sa.Column('valid_from', sa.Date(), nullable=True),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # Price Book Entries table
    op.create_table(
        'price_book_entries',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('price_book_id', sa.Integer(), sa.ForeignKey('price_books.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('items.id'), nullable=False),
        sa.Column('min_qty', sa.Numeric(12, 4), default=1),
        sa.Column('max_qty', sa.Numeric(12, 4), nullable=True),
        sa.Column('unit_price', sa.Numeric(12, 4), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_unique_constraint('uq_price_book_entry', 'price_book_entries', ['price_book_id', 'item_id', 'min_qty'])

    # Approval Rules table
    op.create_table(
        'approval_rules',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('condition_type', sa.String(50), nullable=False),
        sa.Column('threshold_value', sa.Numeric(12, 4), nullable=True),
        sa.Column('approver_role', sa.String(50), nullable=False),
        sa.Column('priority', sa.Integer(), default=0),
        sa.Column('active', sa.Boolean(), default=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Estimates table (header)
    op.create_table(
        'estimates',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('estimate_number', sa.String(50), nullable=False),
        sa.Column('version', sa.Integer(), default=1),
        sa.Column('parent_estimate_id', sa.Integer(), sa.ForeignKey('estimates.id'), nullable=True),
        sa.Column('superseded_by_id', sa.Integer(), sa.ForeignKey('estimates.id'), nullable=True),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customers.id'), nullable=False),
        sa.Column('status', sa.Enum('draft', 'pending_approval', 'approved', 'sent', 'accepted', 'rejected', 'expired', name='estimate_status'), default='draft'),
        sa.Column('currency_code', sa.String(3), default='USD'),
        sa.Column('exchange_rate', sa.Numeric(10, 6), default=1.0),
        sa.Column('price_book_id', sa.Integer(), sa.ForeignKey('price_books.id'), nullable=True),
        sa.Column('valid_until', sa.Date(), nullable=True),
        sa.Column('subtotal', sa.Numeric(12, 2), default=0),
        sa.Column('tax_amount', sa.Numeric(12, 2), default=0),
        sa.Column('total_amount', sa.Numeric(12, 2), default=0),
        sa.Column('margin_percent', sa.Numeric(5, 4), nullable=True),
        sa.Column('requested_delivery_date', sa.Date(), nullable=True),
        sa.Column('earliest_delivery_date', sa.Date(), nullable=True),
        sa.Column('delivery_feasible', sa.Boolean(), default=True),
        sa.Column('pending_approvers', JSONB, nullable=True),
        sa.Column('approved_by', sa.Integer(), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('accepted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('metadata', JSONB, nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )
    op.create_unique_constraint('uq_estimate_version', 'estimates', ['estimate_number', 'version'])

    # Estimate Line Items table
    op.create_table(
        'estimate_line_items',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('estimate_id', sa.Integer(), sa.ForeignKey('estimates.id', ondelete='CASCADE'), nullable=False),
        sa.Column('item_id', sa.Integer(), sa.ForeignKey('items.id'), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('quantity', sa.Numeric(12, 4), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 4), nullable=False),
        sa.Column('list_price', sa.Numeric(12, 4), nullable=True),
        sa.Column('unit_cost', sa.Numeric(12, 4), nullable=True),
        sa.Column('discount_pct', sa.Numeric(5, 4), default=0),
        sa.Column('line_total', sa.Numeric(12, 2), nullable=False),
        sa.Column('tax_amount', sa.Numeric(12, 2), default=0),
        sa.Column('atp_status', sa.Enum('available', 'partial', 'backorder', name='atp_status'), default='available'),
        sa.Column('atp_available_qty', sa.Numeric(12, 4), nullable=True),
        sa.Column('atp_shortage_qty', sa.Numeric(12, 4), nullable=True),
        sa.Column('atp_lead_time_days', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), default=0),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Create indexes
    op.create_index('ix_estimates_customer_id', 'estimates', ['customer_id'])
    op.create_index('ix_estimates_status', 'estimates', ['status'])
    op.create_index('ix_estimate_line_items_estimate_id', 'estimate_line_items', ['estimate_id'])


def downgrade() -> None:
    op.drop_index('ix_estimate_line_items_estimate_id')
    op.drop_index('ix_estimates_status')
    op.drop_index('ix_estimates_customer_id')
    op.drop_table('estimate_line_items')
    op.drop_table('estimates')
    op.drop_table('approval_rules')
    op.drop_table('price_book_entries')
    op.drop_table('price_books')
    op.execute('DROP TYPE atp_status')
    op.execute('DROP TYPE estimate_status')
```

**Step 3: Run migration**

Run:
```bash
docker compose exec backend alembic upgrade head
```
Expected: Migration applies successfully

**Step 4: Commit**

```bash
git add backend/alembic/versions/004_add_estimating_module.py
git commit -m "feat(db): add estimating module tables

- PriceBook and PriceBookEntry for pricing tiers
- ApprovalRule for configurable approval gates
- Estimate header with versioning support
- EstimateLineItem with ATP status tracking"
```

---

### Task 1.2: Create SQLAlchemy Models

**Files:**
- Modify: `backend/models.py` (append after existing models)

**Step 1: Add EstimateStatus enum**

Add after `MessageRole` enum (~line 62):

```python
class EstimateStatus(str, enum.Enum):
    """Estimate lifecycle status."""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ATPStatus(str, enum.Enum):
    """Available to Promise status."""
    AVAILABLE = "available"
    PARTIAL = "partial"
    BACKORDER = "backorder"
```

**Step 2: Add PriceBook model**

Add after `Document` model (~line 390):

```python
# ============================================================================
# Estimating Module Models
# ============================================================================

class PriceBook(Base):
    """Price book for customer/tier-specific pricing."""
    __tablename__ = "price_books"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    customer_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("customers.id"), nullable=True
    )
    customer_segment: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    valid_from: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    customer: Mapped[Optional["Customer"]] = relationship()
    entries: Mapped[list["PriceBookEntry"]] = relationship(back_populates="price_book", cascade="all, delete-orphan")


class PriceBookEntry(Base):
    """Individual price entry with optional volume tiers."""
    __tablename__ = "price_book_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    price_book_id: Mapped[int] = mapped_column(
        ForeignKey("price_books.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    min_qty: Mapped[float] = mapped_column(Float, default=1)
    max_qty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    price_book: Mapped["PriceBook"] = relationship(back_populates="entries")
    item: Mapped["Item"] = relationship()


class ApprovalRule(Base):
    """Configurable approval rules for estimates."""
    __tablename__ = "approval_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    condition_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Types: margin_below, total_above, payment_terms_above, customer_new
    threshold_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    approver_role: Mapped[str] = mapped_column(String(50), nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0)
    active: Mapped[bool] = mapped_column(Boolean, default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Estimate(Base):
    """Estimate/Quote header with versioning support."""
    __tablename__ = "estimates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    estimate_number: Mapped[str] = mapped_column(String(50), nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_estimate_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("estimates.id"), nullable=True
    )
    superseded_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("estimates.id"), nullable=True
    )

    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), nullable=False)
    status: Mapped[EstimateStatus] = mapped_column(
        Enum(EstimateStatus), default=EstimateStatus.DRAFT
    )

    currency_code: Mapped[str] = mapped_column(String(3), default="USD")
    exchange_rate: Mapped[float] = mapped_column(Float, default=1.0)
    price_book_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("price_books.id"), nullable=True
    )

    valid_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    subtotal: Mapped[float] = mapped_column(Float, default=0)
    tax_amount: Mapped[float] = mapped_column(Float, default=0)
    total_amount: Mapped[float] = mapped_column(Float, default=0)
    margin_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    requested_delivery_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    earliest_delivery_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    delivery_feasible: Mapped[bool] = mapped_column(Boolean, default=True)

    pending_approvers: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    approved_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    metadata: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    customer: Mapped["Customer"] = relationship()
    price_book: Mapped[Optional["PriceBook"]] = relationship()
    line_items: Mapped[list["EstimateLineItem"]] = relationship(
        back_populates="estimate", cascade="all, delete-orphan", order_by="EstimateLineItem.sort_order"
    )
    parent_estimate: Mapped[Optional["Estimate"]] = relationship(
        remote_side=[id], foreign_keys=[parent_estimate_id]
    )


class EstimateLineItem(Base):
    """Individual line item on an estimate."""
    __tablename__ = "estimate_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    estimate_id: Mapped[int] = mapped_column(
        ForeignKey("estimates.id", ondelete="CASCADE"), nullable=False
    )
    item_id: Mapped[Optional[int]] = mapped_column(ForeignKey("items.id"), nullable=True)
    description: Mapped[str] = mapped_column(Text, nullable=False)

    quantity: Mapped[float] = mapped_column(Float, nullable=False)
    unit_price: Mapped[float] = mapped_column(Float, nullable=False)
    list_price: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit_cost: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    discount_pct: Mapped[float] = mapped_column(Float, default=0)
    line_total: Mapped[float] = mapped_column(Float, nullable=False)
    tax_amount: Mapped[float] = mapped_column(Float, default=0)

    atp_status: Mapped[ATPStatus] = mapped_column(
        Enum(ATPStatus), default=ATPStatus.AVAILABLE
    )
    atp_available_qty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    atp_shortage_qty: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    atp_lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    estimate: Mapped["Estimate"] = relationship(back_populates="line_items")
    item: Mapped[Optional["Item"]] = relationship()
```

**Step 3: Verify models load correctly**

Run:
```bash
docker compose exec backend python -c "from models import Estimate, EstimateLineItem, PriceBook, ApprovalRule; print('Models loaded OK')"
```
Expected: "Models loaded OK"

**Step 4: Commit**

```bash
git add backend/models.py
git commit -m "feat(models): add SQLAlchemy models for estimating module

- PriceBook/PriceBookEntry for pricing tiers
- ApprovalRule for configurable approval gates
- Estimate with versioning (parent_estimate_id)
- EstimateLineItem with ATP status tracking"
```

---

### Task 1.3: Create Pydantic Schemas

**Files:**
- Modify: `backend/schemas.py` (append after existing schemas)

**Step 1: Add EstimateStatus and ATPStatus enums**

Add after `MessageRole` enum (~line 40):

```python
class EstimateStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    SENT = "sent"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"


class ATPStatus(str, Enum):
    AVAILABLE = "available"
    PARTIAL = "partial"
    BACKORDER = "backorder"
```

**Step 2: Add estimating schemas**

Add after `CostCalculation` schema (~line 368):

```python
# ============================================================================
# Price Book Schemas
# ============================================================================

class PriceBookEntryBase(BaseSchema):
    item_id: int
    min_qty: float = 1
    max_qty: Optional[float] = None
    unit_price: float = Field(..., gt=0)


class PriceBookEntryCreate(PriceBookEntryBase):
    pass


class PriceBookEntryResponse(PriceBookEntryBase):
    id: int
    price_book_id: int
    created_at: datetime


class PriceBookBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=100)
    is_default: bool = False
    customer_id: Optional[int] = None
    customer_segment: Optional[str] = None
    currency_code: str = "USD"
    valid_from: Optional[datetime] = None
    valid_until: Optional[datetime] = None
    active: bool = True


class PriceBookCreate(PriceBookBase):
    entries: Optional[list[PriceBookEntryCreate]] = None


class PriceBookResponse(PriceBookBase):
    id: int
    created_at: datetime
    updated_at: datetime
    entries: list[PriceBookEntryResponse] = []


# ============================================================================
# Approval Rule Schemas
# ============================================================================

class ApprovalRuleBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=100)
    condition_type: str  # margin_below, total_above, payment_terms_above
    threshold_value: Optional[float] = None
    approver_role: str
    priority: int = 0
    active: bool = True


class ApprovalRuleCreate(ApprovalRuleBase):
    pass


class ApprovalRuleResponse(ApprovalRuleBase):
    id: int
    created_at: datetime


# ============================================================================
# Estimate Line Item Schemas
# ============================================================================

class EstimateLineItemBase(BaseSchema):
    item_id: Optional[int] = None
    description: str = Field(..., min_length=1)
    quantity: float = Field(..., gt=0)
    unit_price: float = Field(..., ge=0)
    discount_pct: float = Field(default=0, ge=0, le=1)
    notes: Optional[str] = None


class EstimateLineItemCreate(EstimateLineItemBase):
    pass


class EstimateLineItemUpdate(BaseSchema):
    description: Optional[str] = None
    quantity: Optional[float] = Field(None, gt=0)
    unit_price: Optional[float] = Field(None, ge=0)
    discount_pct: Optional[float] = Field(None, ge=0, le=1)
    notes: Optional[str] = None


class EstimateLineItemResponse(EstimateLineItemBase):
    id: int
    estimate_id: int
    list_price: Optional[float] = None
    unit_cost: Optional[float] = None
    line_total: float
    tax_amount: float = 0
    atp_status: ATPStatus = ATPStatus.AVAILABLE
    atp_available_qty: Optional[float] = None
    atp_shortage_qty: Optional[float] = None
    atp_lead_time_days: Optional[int] = None
    sort_order: int = 0
    created_at: datetime


# ============================================================================
# Estimate Schemas
# ============================================================================

class EstimateBase(BaseSchema):
    customer_id: int
    valid_until: Optional[datetime] = None
    requested_delivery_date: Optional[datetime] = None
    notes: Optional[str] = None
    currency_code: str = "USD"


class EstimateCreate(EstimateBase):
    line_items: Optional[list[EstimateLineItemCreate]] = None


class EstimateGenerateRequest(BaseSchema):
    """Request for NLP-driven estimate generation."""
    prompt: str = Field(..., min_length=1, max_length=2000)
    thread_id: Optional[str] = None


class EstimateUpdate(BaseSchema):
    valid_until: Optional[datetime] = None
    requested_delivery_date: Optional[datetime] = None
    notes: Optional[str] = None
    price_book_id: Optional[int] = None


class EstimateResponse(EstimateBase):
    id: int
    estimate_number: str
    version: int
    parent_estimate_id: Optional[int] = None
    status: EstimateStatus
    price_book_id: Optional[int] = None
    subtotal: float
    tax_amount: float
    total_amount: float
    margin_percent: Optional[float] = None
    earliest_delivery_date: Optional[datetime] = None
    delivery_feasible: bool = True
    pending_approvers: Optional[list[str]] = None
    approved_by: Optional[int] = None
    approved_at: Optional[datetime] = None
    rejection_reason: Optional[str] = None
    sent_at: Optional[datetime] = None
    accepted_at: Optional[datetime] = None
    metadata: Optional[dict[str, Any]] = None
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: datetime
    line_items: list[EstimateLineItemResponse] = []


class EstimateListResponse(BaseSchema):
    """Lightweight estimate for list views."""
    id: int
    estimate_number: str
    version: int
    customer_id: int
    customer_name: Optional[str] = None
    status: EstimateStatus
    total_amount: float
    valid_until: Optional[datetime] = None
    created_at: datetime


class EstimateActionRequest(BaseSchema):
    """Request for estimate actions (approve, reject, send)."""
    comment: Optional[str] = None


class EstimateRejectRequest(BaseSchema):
    """Request for rejecting an estimate."""
    reason: str = Field(..., min_length=1)


class EstimateVersionResponse(BaseSchema):
    """Version history entry."""
    version: int
    status: EstimateStatus
    created_at: datetime
    changes: Optional[list[str]] = None
    rejection_reason: Optional[str] = None


class ATPWarning(BaseSchema):
    """ATP warning for display."""
    line_item_id: int
    item_name: str
    required_qty: float
    available_qty: float
    shortage_qty: float
    lead_time_days: int
    message: str
```

**Step 3: Add UIResponseType entries**

Find `UIResponseType` enum and add:

```python
class UIResponseType(str, Enum):
    TEXT = "text"
    QUOTE_OPTIONS = "quote_options"
    JOB_STATUS = "job_status"
    SCHEDULE_VIEW = "schedule_view"
    INVENTORY_TABLE = "inventory_table"
    CHART = "chart"
    CONFIRMATION = "confirmation"
    ERROR = "error"
    # New for estimating
    ESTIMATE_CARD = "estimate_card"
    ESTIMATE_LIST = "estimate_list"
    APPROVAL_REQUEST = "approval_request"
    PRODUCT_DISAMBIGUATION = "product_disambiguation"
    ATP_WARNING = "atp_warning"
```

**Step 4: Verify schemas**

Run:
```bash
docker compose exec backend python -c "from schemas import EstimateCreate, EstimateResponse, PriceBookCreate; print('Schemas loaded OK')"
```
Expected: "Schemas loaded OK"

**Step 5: Commit**

```bash
git add backend/schemas.py
git commit -m "feat(schemas): add Pydantic schemas for estimating module

- PriceBook/Entry schemas with validation
- ApprovalRule schemas
- Estimate/LineItem schemas with ATP fields
- EstimateGenerateRequest for NLP endpoint
- ATPWarning for display"
```

---

## Phase 2: Core Services

### Task 2.1: Create Pricing Service

**Files:**
- Create: `backend/services/pricing.py`

**Step 1: Create pricing service**

```python
"""Pricing service for price book resolution and tiered pricing."""

from decimal import Decimal
from typing import Optional
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from models import PriceBook, PriceBookEntry, Item, Customer


class PricingService:
    """Resolves prices from price books with tiered/volume support."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def resolve_price(
        self,
        item_id: int,
        customer_id: int,
        quantity: float = 1
    ) -> tuple[float, Optional[int]]:
        """
        Resolve price for an item based on customer and quantity.

        Returns:
            Tuple of (unit_price, price_book_id used)

        Resolution order:
        1. Customer-specific price book
        2. Customer segment price book
        3. Default price book
        4. Item cost_per_unit as fallback
        """
        # 1. Check customer-specific price book
        customer_book = await self._get_customer_price_book(customer_id)
        if customer_book:
            price = await self._get_tiered_price(customer_book.id, item_id, quantity)
            if price is not None:
                return price, customer_book.id

        # 2. Check segment price book
        customer = await self.db.get(Customer, customer_id)
        if customer and customer.extra_data and customer.extra_data.get("segment"):
            segment = customer.extra_data["segment"]
            segment_book = await self._get_segment_price_book(segment)
            if segment_book:
                price = await self._get_tiered_price(segment_book.id, item_id, quantity)
                if price is not None:
                    return price, segment_book.id

        # 3. Check default price book
        default_book = await self._get_default_price_book()
        if default_book:
            price = await self._get_tiered_price(default_book.id, item_id, quantity)
            if price is not None:
                return price, default_book.id

        # 4. Fallback to item cost
        item = await self.db.get(Item, item_id)
        if item:
            return float(item.cost_per_unit), None

        raise ValueError(f"Item {item_id} not found")

    async def _get_customer_price_book(self, customer_id: int) -> Optional[PriceBook]:
        """Get active price book for specific customer."""
        result = await self.db.execute(
            select(PriceBook)
            .where(PriceBook.customer_id == customer_id)
            .where(PriceBook.active == True)
        )
        return result.scalar_one_or_none()

    async def _get_segment_price_book(self, segment: str) -> Optional[PriceBook]:
        """Get active price book for customer segment."""
        result = await self.db.execute(
            select(PriceBook)
            .where(PriceBook.customer_segment == segment)
            .where(PriceBook.customer_id.is_(None))
            .where(PriceBook.active == True)
        )
        return result.scalar_one_or_none()

    async def _get_default_price_book(self) -> Optional[PriceBook]:
        """Get default price book."""
        result = await self.db.execute(
            select(PriceBook)
            .where(PriceBook.is_default == True)
            .where(PriceBook.active == True)
        )
        return result.scalar_one_or_none()

    async def _get_tiered_price(
        self,
        price_book_id: int,
        item_id: int,
        quantity: float
    ) -> Optional[float]:
        """Get price from price book applying volume tier."""
        # Find the entry where quantity falls within min/max range
        result = await self.db.execute(
            select(PriceBookEntry)
            .where(PriceBookEntry.price_book_id == price_book_id)
            .where(PriceBookEntry.item_id == item_id)
            .where(PriceBookEntry.min_qty <= quantity)
            .where(
                (PriceBookEntry.max_qty.is_(None)) |
                (PriceBookEntry.max_qty >= quantity)
            )
            .order_by(PriceBookEntry.min_qty.desc())
            .limit(1)
        )
        entry = result.scalar_one_or_none()
        return float(entry.unit_price) if entry else None

    async def get_list_price(self, item_id: int) -> Optional[float]:
        """Get standard list price from default price book."""
        default_book = await self._get_default_price_book()
        if default_book:
            return await self._get_tiered_price(default_book.id, item_id, 1)
        return None

    async def create_price_book(
        self,
        name: str,
        is_default: bool = False,
        customer_id: Optional[int] = None,
        customer_segment: Optional[str] = None,
        currency_code: str = "USD"
    ) -> PriceBook:
        """Create a new price book."""
        # If setting as default, unset other defaults
        if is_default:
            await self.db.execute(
                select(PriceBook)
                .where(PriceBook.is_default == True)
            )
            result = await self.db.execute(
                select(PriceBook).where(PriceBook.is_default == True)
            )
            for book in result.scalars():
                book.is_default = False

        price_book = PriceBook(
            name=name,
            is_default=is_default,
            customer_id=customer_id,
            customer_segment=customer_segment,
            currency_code=currency_code,
            active=True
        )
        self.db.add(price_book)
        await self.db.flush()
        return price_book

    async def add_price_book_entry(
        self,
        price_book_id: int,
        item_id: int,
        unit_price: float,
        min_qty: float = 1,
        max_qty: Optional[float] = None
    ) -> PriceBookEntry:
        """Add entry to price book."""
        entry = PriceBookEntry(
            price_book_id=price_book_id,
            item_id=item_id,
            unit_price=unit_price,
            min_qty=min_qty,
            max_qty=max_qty
        )
        self.db.add(entry)
        await self.db.flush()
        return entry
```

**Step 2: Verify service**

Run:
```bash
docker compose exec backend python -c "from services.pricing import PricingService; print('PricingService loaded OK')"
```
Expected: "PricingService loaded OK"

**Step 3: Commit**

```bash
git add backend/services/pricing.py
git commit -m "feat(services): add PricingService for price book resolution

- Customer-specific price book lookup
- Segment-based price book lookup
- Default price book fallback
- Tiered/volume pricing support
- Price book and entry CRUD"
```

---

### Task 2.2: Create ATP Service

**Files:**
- Create: `backend/services/atp.py`

**Step 1: Create ATP service**

```python
"""Available to Promise (ATP) service for inventory and delivery checks."""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Item, ATPStatus
from schemas import ATPWarning


class ATPService:
    """Checks inventory availability and calculates delivery feasibility."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def check_availability(
        self,
        item_id: int,
        quantity_required: float
    ) -> dict:
        """
        Check availability of an item.

        Returns:
            Dict with atp_status, available_qty, shortage_qty, lead_time_days
        """
        item = await self.db.get(Item, item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found")

        available = float(item.quantity_on_hand)
        required = float(quantity_required)

        if available >= required:
            return {
                "atp_status": ATPStatus.AVAILABLE,
                "atp_available_qty": available,
                "atp_shortage_qty": 0,
                "atp_lead_time_days": 0
            }
        elif available > 0:
            return {
                "atp_status": ATPStatus.PARTIAL,
                "atp_available_qty": available,
                "atp_shortage_qty": required - available,
                "atp_lead_time_days": item.vendor_lead_time_days
            }
        else:
            return {
                "atp_status": ATPStatus.BACKORDER,
                "atp_available_qty": 0,
                "atp_shortage_qty": required,
                "atp_lead_time_days": item.vendor_lead_time_days
            }

    async def calculate_earliest_delivery(
        self,
        line_items: list[dict],
        requested_date: Optional[datetime] = None
    ) -> tuple[datetime, bool, list[ATPWarning]]:
        """
        Calculate earliest possible delivery date based on line items.

        Args:
            line_items: List of dicts with item_id and quantity
            requested_date: Customer's requested delivery date

        Returns:
            Tuple of (earliest_date, is_feasible, warnings)
        """
        today = datetime.utcnow().date()
        max_lead_time = 0
        warnings = []

        for line in line_items:
            item_id = line.get("item_id")
            if not item_id:
                continue

            quantity = line.get("quantity", 1)
            atp = await self.check_availability(item_id, quantity)

            if atp["atp_status"] != ATPStatus.AVAILABLE:
                item = await self.db.get(Item, item_id)
                lead_time = atp["atp_lead_time_days"] or 0
                max_lead_time = max(max_lead_time, lead_time)

                warnings.append(ATPWarning(
                    line_item_id=line.get("id", 0),
                    item_name=item.name if item else f"Item {item_id}",
                    required_qty=quantity,
                    available_qty=atp["atp_available_qty"],
                    shortage_qty=atp["atp_shortage_qty"],
                    lead_time_days=lead_time,
                    message=self._format_warning(atp, item.name if item else "Item")
                ))

        # Add processing time (2 days minimum)
        processing_days = 2
        earliest_date = datetime.combine(
            today + timedelta(days=max_lead_time + processing_days),
            datetime.min.time()
        )

        is_feasible = True
        if requested_date:
            is_feasible = earliest_date.date() <= requested_date.date()

        return earliest_date, is_feasible, warnings

    def _format_warning(self, atp: dict, item_name: str) -> str:
        """Format ATP warning message."""
        status = atp["atp_status"]
        shortage = atp["atp_shortage_qty"]
        lead_time = atp["atp_lead_time_days"]

        if status == ATPStatus.PARTIAL:
            return f"{shortage:.0f} units of {item_name} backordered (+{lead_time} days)"
        elif status == ATPStatus.BACKORDER:
            return f"{item_name} not in stock. Lead time: {lead_time} days"
        return ""

    async def get_line_item_atp(
        self,
        item_id: int,
        quantity: float
    ) -> dict:
        """Get ATP data for a single line item."""
        atp = await self.check_availability(item_id, quantity)
        return {
            "atp_status": atp["atp_status"],
            "atp_available_qty": atp["atp_available_qty"],
            "atp_shortage_qty": atp["atp_shortage_qty"],
            "atp_lead_time_days": atp["atp_lead_time_days"]
        }
```

**Step 2: Verify service**

Run:
```bash
docker compose exec backend python -c "from services.atp import ATPService; print('ATPService loaded OK')"
```
Expected: "ATPService loaded OK"

**Step 3: Commit**

```bash
git add backend/services/atp.py
git commit -m "feat(services): add ATPService for availability checks

- Check item availability against inventory
- Calculate earliest delivery date
- Generate ATP warnings for partial/backorder
- Support line item-level ATP status"
```

---

### Task 2.3: Create Estimate Service

**Files:**
- Create: `backend/services/estimate.py`

**Step 1: Create estimate service**

```python
"""Estimate service for CRUD, versioning, and status transitions."""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import (
    Estimate, EstimateLineItem, EstimateStatus, ATPStatus,
    Customer, Item, ApprovalRule
)
from schemas import (
    EstimateCreate, EstimateLineItemCreate, EstimateUpdate,
    EstimateLineItemUpdate
)
from services.pricing import PricingService
from services.atp import ATPService


class EstimateService:
    """Manages estimate lifecycle, versioning, and calculations."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.pricing = PricingService(db)
        self.atp = ATPService(db)

    async def create_estimate(
        self,
        customer_id: int,
        line_items: Optional[list[EstimateLineItemCreate]] = None,
        valid_days: int = 30,
        requested_delivery_date: Optional[datetime] = None,
        notes: Optional[str] = None,
        created_by: Optional[int] = None
    ) -> Estimate:
        """Create a new estimate with optional line items."""
        # Generate estimate number
        estimate_number = await self._generate_estimate_number()

        estimate = Estimate(
            estimate_number=estimate_number,
            version=1,
            customer_id=customer_id,
            status=EstimateStatus.DRAFT,
            valid_until=datetime.utcnow() + timedelta(days=valid_days),
            requested_delivery_date=requested_delivery_date,
            notes=notes,
            created_by=created_by
        )
        self.db.add(estimate)
        await self.db.flush()

        # Add line items if provided
        if line_items:
            for i, item_data in enumerate(line_items):
                await self.add_line_item(estimate.id, item_data, sort_order=i)

        # Recalculate totals
        await self._recalculate_totals(estimate)

        await self.db.flush()
        return estimate

    async def get_estimate(self, estimate_id: int) -> Optional[Estimate]:
        """Get estimate with all line items."""
        result = await self.db.execute(
            select(Estimate)
            .options(selectinload(Estimate.line_items))
            .options(selectinload(Estimate.customer))
            .where(Estimate.id == estimate_id)
        )
        return result.scalar_one_or_none()

    async def get_estimate_by_number(
        self,
        estimate_number: str,
        version: Optional[int] = None
    ) -> Optional[Estimate]:
        """Get estimate by number, optionally specific version."""
        query = select(Estimate).where(Estimate.estimate_number == estimate_number)
        if version:
            query = query.where(Estimate.version == version)
        else:
            # Get latest version
            query = query.order_by(Estimate.version.desc()).limit(1)

        result = await self.db.execute(
            query.options(selectinload(Estimate.line_items))
        )
        return result.scalar_one_or_none()

    async def list_estimates(
        self,
        customer_id: Optional[int] = None,
        status: Optional[EstimateStatus] = None,
        limit: int = 50
    ) -> list[Estimate]:
        """List estimates with optional filters."""
        query = select(Estimate).order_by(Estimate.created_at.desc())

        if customer_id:
            query = query.where(Estimate.customer_id == customer_id)
        if status:
            query = query.where(Estimate.status == status)

        query = query.limit(limit)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def add_line_item(
        self,
        estimate_id: int,
        item_data: EstimateLineItemCreate,
        sort_order: Optional[int] = None
    ) -> EstimateLineItem:
        """Add line item to estimate with price and ATP resolution."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.DRAFT:
            raise ValueError("Can only add lines to draft estimates")

        # Resolve pricing
        unit_price = item_data.unit_price
        list_price = None
        unit_cost = None
        price_book_id = None

        if item_data.item_id:
            unit_price, price_book_id = await self.pricing.resolve_price(
                item_data.item_id,
                estimate.customer_id,
                item_data.quantity
            )
            list_price = await self.pricing.get_list_price(item_data.item_id)

            # Get item cost
            item = await self.db.get(Item, item_data.item_id)
            if item:
                unit_cost = float(item.cost_per_unit)

        # Apply discount
        if item_data.discount_pct:
            unit_price = unit_price * (1 - item_data.discount_pct)

        # Calculate line total
        line_total = unit_price * item_data.quantity

        # Check ATP
        atp_data = {}
        if item_data.item_id:
            atp_data = await self.atp.get_line_item_atp(
                item_data.item_id,
                item_data.quantity
            )

        # Determine sort order
        if sort_order is None:
            result = await self.db.execute(
                select(func.max(EstimateLineItem.sort_order))
                .where(EstimateLineItem.estimate_id == estimate_id)
            )
            max_order = result.scalar() or 0
            sort_order = max_order + 1

        line_item = EstimateLineItem(
            estimate_id=estimate_id,
            item_id=item_data.item_id,
            description=item_data.description,
            quantity=item_data.quantity,
            unit_price=unit_price,
            list_price=list_price,
            unit_cost=unit_cost,
            discount_pct=item_data.discount_pct or 0,
            line_total=line_total,
            sort_order=sort_order,
            notes=item_data.notes,
            **atp_data
        )
        self.db.add(line_item)
        await self.db.flush()

        # Recalculate totals
        await self._recalculate_totals(estimate)

        return line_item

    async def update_line_item(
        self,
        line_item_id: int,
        updates: EstimateLineItemUpdate
    ) -> EstimateLineItem:
        """Update line item and recalculate."""
        line_item = await self.db.get(EstimateLineItem, line_item_id)
        if not line_item:
            raise ValueError(f"Line item {line_item_id} not found")

        estimate = await self.get_estimate(line_item.estimate_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise ValueError("Can only update lines on draft estimates")

        # Apply updates
        if updates.description is not None:
            line_item.description = updates.description
        if updates.quantity is not None:
            line_item.quantity = updates.quantity
        if updates.unit_price is not None:
            line_item.unit_price = updates.unit_price
        if updates.discount_pct is not None:
            line_item.discount_pct = updates.discount_pct
        if updates.notes is not None:
            line_item.notes = updates.notes

        # Recalculate line total
        effective_price = line_item.unit_price * (1 - line_item.discount_pct)
        line_item.line_total = effective_price * line_item.quantity

        # Re-check ATP if quantity changed
        if updates.quantity is not None and line_item.item_id:
            atp_data = await self.atp.get_line_item_atp(
                line_item.item_id,
                line_item.quantity
            )
            line_item.atp_status = atp_data["atp_status"]
            line_item.atp_available_qty = atp_data["atp_available_qty"]
            line_item.atp_shortage_qty = atp_data["atp_shortage_qty"]
            line_item.atp_lead_time_days = atp_data["atp_lead_time_days"]

        await self.db.flush()

        # Recalculate estimate totals
        await self._recalculate_totals(estimate)

        return line_item

    async def delete_line_item(self, line_item_id: int) -> None:
        """Delete line item."""
        line_item = await self.db.get(EstimateLineItem, line_item_id)
        if not line_item:
            return

        estimate = await self.get_estimate(line_item.estimate_id)
        if estimate.status != EstimateStatus.DRAFT:
            raise ValueError("Can only delete lines from draft estimates")

        await self.db.delete(line_item)
        await self.db.flush()

        # Recalculate totals
        await self._recalculate_totals(estimate)

    async def submit_for_approval(self, estimate_id: int) -> Estimate:
        """Submit estimate for approval, checking rules."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.DRAFT:
            raise ValueError("Can only submit draft estimates")

        if not estimate.line_items:
            raise ValueError("Cannot submit estimate with no line items")

        # Check delivery feasibility - block if impossible
        if not estimate.delivery_feasible:
            raise ValueError(
                f"Cannot submit: requested delivery date cannot be met. "
                f"Earliest possible: {estimate.earliest_delivery_date}"
            )

        # Check approval rules
        triggered_rules = await self._check_approval_rules(estimate)

        if triggered_rules:
            estimate.status = EstimateStatus.PENDING_APPROVAL
            estimate.pending_approvers = [r.approver_role for r in triggered_rules]
        else:
            estimate.status = EstimateStatus.APPROVED

        await self.db.flush()
        return estimate

    async def approve(
        self,
        estimate_id: int,
        approved_by: int,
        comment: Optional[str] = None
    ) -> Estimate:
        """Approve pending estimate."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.PENDING_APPROVAL:
            raise ValueError("Can only approve pending estimates")

        estimate.status = EstimateStatus.APPROVED
        estimate.approved_by = approved_by
        estimate.approved_at = datetime.utcnow()
        estimate.pending_approvers = None

        if comment:
            estimate.notes = f"{estimate.notes or ''}\n\nApproval: {comment}".strip()

        await self.db.flush()
        return estimate

    async def reject(
        self,
        estimate_id: int,
        reason: str
    ) -> Estimate:
        """Reject pending estimate."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.PENDING_APPROVAL:
            raise ValueError("Can only reject pending estimates")

        estimate.status = EstimateStatus.REJECTED
        estimate.rejection_reason = reason
        estimate.pending_approvers = None

        await self.db.flush()
        return estimate

    async def send_to_customer(self, estimate_id: int) -> Estimate:
        """Mark estimate as sent to customer."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.APPROVED:
            raise ValueError("Can only send approved estimates")

        estimate.status = EstimateStatus.SENT
        estimate.sent_at = datetime.utcnow()

        await self.db.flush()
        return estimate

    async def accept(self, estimate_id: int) -> Estimate:
        """Mark estimate as accepted by customer."""
        estimate = await self.get_estimate(estimate_id)
        if not estimate:
            raise ValueError(f"Estimate {estimate_id} not found")

        if estimate.status != EstimateStatus.SENT:
            raise ValueError("Can only accept sent estimates")

        estimate.status = EstimateStatus.ACCEPTED
        estimate.accepted_at = datetime.utcnow()

        await self.db.flush()
        return estimate

    async def create_revision(self, estimate_id: int) -> Estimate:
        """Create new version of estimate."""
        original = await self.get_estimate(estimate_id)
        if not original:
            raise ValueError(f"Estimate {estimate_id} not found")

        if original.status not in [EstimateStatus.SENT, EstimateStatus.REJECTED]:
            raise ValueError("Can only revise sent or rejected estimates")

        # Create new version
        new_estimate = Estimate(
            estimate_number=original.estimate_number,
            version=original.version + 1,
            parent_estimate_id=original.id,
            customer_id=original.customer_id,
            status=EstimateStatus.DRAFT,
            currency_code=original.currency_code,
            price_book_id=original.price_book_id,
            valid_until=datetime.utcnow() + timedelta(days=30),
            requested_delivery_date=original.requested_delivery_date,
            notes=original.notes
        )
        self.db.add(new_estimate)
        await self.db.flush()

        # Clone line items
        for line in original.line_items:
            new_line = EstimateLineItem(
                estimate_id=new_estimate.id,
                item_id=line.item_id,
                description=line.description,
                quantity=line.quantity,
                unit_price=line.unit_price,
                list_price=line.list_price,
                unit_cost=line.unit_cost,
                discount_pct=line.discount_pct,
                line_total=line.line_total,
                sort_order=line.sort_order,
                notes=line.notes
            )
            self.db.add(new_line)

        # Mark original as superseded
        original.superseded_by_id = new_estimate.id

        await self.db.flush()

        # Recalculate (re-checks ATP)
        await self._recalculate_totals(new_estimate)

        return new_estimate

    async def get_version_history(self, estimate_number: str) -> list[dict]:
        """Get version history for an estimate."""
        result = await self.db.execute(
            select(Estimate)
            .where(Estimate.estimate_number == estimate_number)
            .order_by(Estimate.version.desc())
        )
        estimates = list(result.scalars().all())

        history = []
        for est in estimates:
            history.append({
                "version": est.version,
                "status": est.status.value,
                "created_at": est.created_at.isoformat(),
                "rejection_reason": est.rejection_reason
            })
        return history

    async def _generate_estimate_number(self) -> str:
        """Generate unique estimate number."""
        today = datetime.utcnow().strftime("%Y%m%d")
        prefix = f"E-{today}"

        result = await self.db.execute(
            select(func.count(Estimate.id))
            .where(Estimate.estimate_number.like(f"{prefix}%"))
        )
        count = result.scalar() or 0

        return f"{prefix}-{count + 1:04d}"

    async def _recalculate_totals(self, estimate: Estimate) -> None:
        """Recalculate estimate totals and delivery date."""
        # Reload line items
        result = await self.db.execute(
            select(EstimateLineItem)
            .where(EstimateLineItem.estimate_id == estimate.id)
        )
        line_items = list(result.scalars().all())

        # Calculate subtotal
        subtotal = sum(line.line_total for line in line_items)
        estimate.subtotal = subtotal

        # Calculate tax (simplified - 8% flat rate for now)
        estimate.tax_amount = subtotal * 0.08
        estimate.total_amount = subtotal + estimate.tax_amount

        # Calculate margin
        total_cost = sum(
            (line.unit_cost or 0) * line.quantity
            for line in line_items
        )
        if subtotal > 0:
            estimate.margin_percent = (subtotal - total_cost) / subtotal
        else:
            estimate.margin_percent = 0

        # Calculate earliest delivery
        line_data = [
            {"id": line.id, "item_id": line.item_id, "quantity": line.quantity}
            for line in line_items if line.item_id
        ]
        earliest, feasible, _ = await self.atp.calculate_earliest_delivery(
            line_data,
            estimate.requested_delivery_date
        )
        estimate.earliest_delivery_date = earliest
        estimate.delivery_feasible = feasible

        await self.db.flush()

    async def _check_approval_rules(self, estimate: Estimate) -> list[ApprovalRule]:
        """Check which approval rules are triggered."""
        result = await self.db.execute(
            select(ApprovalRule)
            .where(ApprovalRule.active == True)
            .order_by(ApprovalRule.priority)
        )
        rules = list(result.scalars().all())

        triggered = []
        for rule in rules:
            if self._rule_applies(rule, estimate):
                triggered.append(rule)

        return triggered

    def _rule_applies(self, rule: ApprovalRule, estimate: Estimate) -> bool:
        """Check if a specific rule applies to the estimate."""
        if rule.condition_type == "margin_below":
            return (estimate.margin_percent or 0) < (rule.threshold_value or 0)
        elif rule.condition_type == "total_above":
            return estimate.total_amount > (rule.threshold_value or 0)
        elif rule.condition_type == "payment_terms_above":
            # Would check customer payment terms
            return False
        return False
```

**Step 2: Verify service**

Run:
```bash
docker compose exec backend python -c "from services.estimate import EstimateService; print('EstimateService loaded OK')"
```
Expected: "EstimateService loaded OK"

**Step 3: Commit**

```bash
git add backend/services/estimate.py
git commit -m "feat(services): add EstimateService for estimate lifecycle

- Create estimates with line items
- Price resolution via PricingService
- ATP checks via ATPService
- Approval workflow (submit, approve, reject)
- Version creation for revisions
- Total/margin/delivery recalculation"
```

---

## Phase 3: API Endpoints

### Task 3.1: Create Estimate API Routes

**Files:**
- Create: `backend/routers/estimates.py`
- Modify: `backend/main.py` (add router)

**Step 1: Create estimates router**

```python
"""API routes for estimates."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from schemas import (
    EstimateCreate, EstimateResponse, EstimateListResponse,
    EstimateUpdate, EstimateGenerateRequest,
    EstimateLineItemCreate, EstimateLineItemUpdate, EstimateLineItemResponse,
    EstimateActionRequest, EstimateRejectRequest, EstimateVersionResponse,
    EstimateStatus
)
from services.estimate import EstimateService

router = APIRouter(prefix="/api/v1/estimates", tags=["Estimates"])


@router.post("", response_model=EstimateResponse, status_code=201)
async def create_estimate(
    data: EstimateCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new estimate."""
    service = EstimateService(db)
    estimate = await service.create_estimate(
        customer_id=data.customer_id,
        line_items=data.line_items,
        requested_delivery_date=data.requested_delivery_date,
        notes=data.notes
    )
    await db.commit()
    return estimate


@router.post("/generate", response_model=EstimateResponse, status_code=201)
async def generate_estimate(
    data: EstimateGenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """Generate estimate from natural language prompt."""
    # This will be implemented in the NLP pipeline task
    raise HTTPException(status_code=501, detail="NLP generation not yet implemented")


@router.get("", response_model=list[EstimateListResponse])
async def list_estimates(
    customer_id: Optional[int] = Query(None),
    status: Optional[EstimateStatus] = Query(None),
    limit: int = Query(50, le=100),
    db: AsyncSession = Depends(get_db)
):
    """List estimates with optional filters."""
    service = EstimateService(db)
    estimates = await service.list_estimates(
        customer_id=customer_id,
        status=status,
        limit=limit
    )

    # Map to list response with customer name
    result = []
    for est in estimates:
        result.append(EstimateListResponse(
            id=est.id,
            estimate_number=est.estimate_number,
            version=est.version,
            customer_id=est.customer_id,
            customer_name=est.customer.name if est.customer else None,
            status=est.status,
            total_amount=est.total_amount,
            valid_until=est.valid_until,
            created_at=est.created_at
        ))
    return result


@router.get("/{estimate_id}", response_model=EstimateResponse)
async def get_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get estimate by ID."""
    service = EstimateService(db)
    estimate = await service.get_estimate(estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")
    return estimate


@router.patch("/{estimate_id}", response_model=EstimateResponse)
async def update_estimate(
    estimate_id: int,
    data: EstimateUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update estimate header fields."""
    service = EstimateService(db)
    estimate = await service.get_estimate(estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    if estimate.status != EstimateStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Can only update draft estimates")

    # Apply updates
    if data.valid_until is not None:
        estimate.valid_until = data.valid_until
    if data.requested_delivery_date is not None:
        estimate.requested_delivery_date = data.requested_delivery_date
    if data.notes is not None:
        estimate.notes = data.notes
    if data.price_book_id is not None:
        estimate.price_book_id = data.price_book_id

    await db.commit()
    return estimate


@router.delete("/{estimate_id}", status_code=204)
async def delete_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete draft estimate."""
    service = EstimateService(db)
    estimate = await service.get_estimate(estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    if estimate.status != EstimateStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Can only delete draft estimates")

    await db.delete(estimate)
    await db.commit()


# Line item routes
@router.post("/{estimate_id}/lines", response_model=EstimateLineItemResponse, status_code=201)
async def add_line_item(
    estimate_id: int,
    data: EstimateLineItemCreate,
    db: AsyncSession = Depends(get_db)
):
    """Add line item to estimate."""
    service = EstimateService(db)
    try:
        line_item = await service.add_line_item(estimate_id, data)
        await db.commit()
        return line_item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.patch("/{estimate_id}/lines/{line_id}", response_model=EstimateLineItemResponse)
async def update_line_item(
    estimate_id: int,
    line_id: int,
    data: EstimateLineItemUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update line item."""
    service = EstimateService(db)
    try:
        line_item = await service.update_line_item(line_id, data)
        await db.commit()
        return line_item
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{estimate_id}/lines/{line_id}", status_code=204)
async def delete_line_item(
    estimate_id: int,
    line_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Delete line item."""
    service = EstimateService(db)
    try:
        await service.delete_line_item(line_id)
        await db.commit()
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# Action routes
@router.post("/{estimate_id}/actions/submit", response_model=EstimateResponse)
async def submit_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Submit estimate for approval."""
    service = EstimateService(db)
    try:
        estimate = await service.submit_for_approval(estimate_id)
        await db.commit()
        return estimate
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{estimate_id}/actions/approve", response_model=EstimateResponse)
async def approve_estimate(
    estimate_id: int,
    data: EstimateActionRequest,
    db: AsyncSession = Depends(get_db)
):
    """Approve pending estimate."""
    service = EstimateService(db)
    try:
        # TODO: Get actual user ID from auth
        estimate = await service.approve(estimate_id, approved_by=1, comment=data.comment)
        await db.commit()
        return estimate
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{estimate_id}/actions/reject", response_model=EstimateResponse)
async def reject_estimate(
    estimate_id: int,
    data: EstimateRejectRequest,
    db: AsyncSession = Depends(get_db)
):
    """Reject pending estimate."""
    service = EstimateService(db)
    try:
        estimate = await service.reject(estimate_id, reason=data.reason)
        await db.commit()
        return estimate
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{estimate_id}/actions/send", response_model=EstimateResponse)
async def send_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Send estimate to customer."""
    service = EstimateService(db)
    try:
        estimate = await service.send_to_customer(estimate_id)
        await db.commit()
        return estimate
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{estimate_id}/actions/accept", response_model=EstimateResponse)
async def accept_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Accept estimate (customer accepted)."""
    service = EstimateService(db)
    try:
        estimate = await service.accept(estimate_id)
        await db.commit()
        return estimate
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{estimate_id}/actions/revise", response_model=EstimateResponse)
async def revise_estimate(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Create new version of estimate."""
    service = EstimateService(db)
    try:
        estimate = await service.create_revision(estimate_id)
        await db.commit()
        return estimate
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{estimate_id}/versions", response_model=list[EstimateVersionResponse])
async def get_version_history(
    estimate_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get version history for estimate."""
    service = EstimateService(db)
    estimate = await service.get_estimate(estimate_id)
    if not estimate:
        raise HTTPException(status_code=404, detail="Estimate not found")

    history = await service.get_version_history(estimate.estimate_number)
    return [EstimateVersionResponse(**h) for h in history]
```

**Step 2: Register router in main.py**

Find the router registration section and add:

```python
from routers.estimates import router as estimates_router
app.include_router(estimates_router)
```

**Step 3: Create routers directory if needed**

Run:
```bash
mkdir -p backend/routers && touch backend/routers/__init__.py
```

**Step 4: Verify API loads**

Run:
```bash
docker compose restart backend && sleep 5 && curl -s http://localhost:8000/docs | grep -o "estimates" | head -1
```
Expected: "estimates"

**Step 5: Commit**

```bash
git add backend/routers/ backend/main.py
git commit -m "feat(api): add estimate REST API endpoints

- CRUD for estimates and line items
- Action endpoints: submit, approve, reject, send, accept
- Version history endpoint
- NLP generate endpoint (stub)"
```

---

## Continue with remaining tasks...

The plan continues with:
- **Task 3.2**: Price Book API routes
- **Task 3.3**: Approval Rule API routes
- **Phase 4**: NLP Pipeline (entity extraction, product resolution, customer history)
- **Phase 5**: Hub Integration (new intents and nodes)
- **Phase 6**: Frontend Components
- **Phase 7**: PDF Generation

---

**Plan Summary:**

| Phase | Tasks | Description |
|-------|-------|-------------|
| 1 | 1.1-1.3 | Database: Migration, Models, Schemas |
| 2 | 2.1-2.3 | Services: Pricing, ATP, Estimate |
| 3 | 3.1-3.3 | API: Estimates, PriceBooks, ApprovalRules |
| 4 | 4.1-4.3 | NLP: Extraction, Product RAG, Customer History |
| 5 | 5.1-5.2 | Hub: New Intents, Estimate Nodes |
| 6 | 6.1-6.4 | Frontend: Card, Modal, LineTable, Warnings |
| 7 | 7.1-7.2 | PDF: Service, Template |

**Estimated total tasks:** 18 bite-sized tasks
