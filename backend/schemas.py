"""Pydantic V2 schemas for API validation."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ============================================================================
# Enums (matching SQLAlchemy models)
# ============================================================================

class JobStatus(str, Enum):
    DRAFT = "draft"
    QUOTED = "quoted"
    SCHEDULED = "scheduled"
    FINANCIAL_HOLD = "financial_hold"
    IN_PRODUCTION = "in_production"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class QuoteType(str, Enum):
    FASTEST = "fastest"
    CHEAPEST = "cheapest"
    BALANCED = "balanced"


class SlotStatus(str, Enum):
    AVAILABLE = "available"
    RESERVED = "reserved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ============================================================================
# Base Schemas
# ============================================================================

class BaseSchema(BaseModel):
    """Base schema with common configuration."""
    model_config = ConfigDict(from_attributes=True)


# ============================================================================
# Item Schemas
# ============================================================================

class ItemBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    sku: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    quantity_on_hand: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=10, ge=0)
    cost_per_unit: float = Field(..., gt=0)
    vendor_lead_time_days: int = Field(default=7, ge=0)
    vendor_name: Optional[str] = None
    category: Optional[str] = None
    uom: str = Field(default="each", max_length=20)  # Unit of Measure
    specifications: Optional[dict[str, Any]] = None


class ItemCreate(ItemBase):
    pass


class ItemUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = None
    quantity_on_hand: Optional[int] = Field(None, ge=0)
    reorder_point: Optional[int] = Field(None, ge=0)
    cost_per_unit: Optional[float] = Field(None, gt=0)
    vendor_lead_time_days: Optional[int] = Field(None, ge=0)
    vendor_name: Optional[str] = None
    category: Optional[str] = None
    uom: Optional[str] = Field(None, max_length=20)
    specifications: Optional[dict[str, Any]] = None


class ItemResponse(ItemBase):
    id: int
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Customer Schemas
# ============================================================================

class CustomerBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    billing_address: Optional[str] = None
    active: bool = True
    notes: Optional[str] = None
    credit_limit: Optional[float] = Field(None, ge=0)
    payment_terms_days: int = Field(default=30, ge=0)


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseSchema):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=50)
    address: Optional[str] = None
    billing_address: Optional[str] = None
    active: Optional[bool] = None
    notes: Optional[str] = None
    credit_limit: Optional[float] = Field(None, ge=0)
    payment_terms_days: Optional[int] = Field(None, ge=0)


class CustomerResponse(CustomerBase):
    id: int
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Machine Schemas
# ============================================================================

class MachineBase(BaseSchema):
    name: str = Field(..., min_length=1, max_length=255)
    machine_type: str = Field(..., min_length=1, max_length=100)
    hourly_rate: float = Field(..., gt=0)
    capabilities: Optional[dict[str, Any]] = None
    status: str = "operational"
    location: Optional[str] = None


class MachineCreate(MachineBase):
    pass


class MachineResponse(MachineBase):
    id: int
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Job Schemas
# ============================================================================

class JobBase(BaseSchema):
    customer_name: str = Field(..., min_length=1, max_length=255)
    customer_email: Optional[str] = None
    description: Optional[str] = None
    priority: int = Field(default=5, ge=1, le=10)
    requested_delivery_date: Optional[datetime] = None
    extra_data: Optional[dict[str, Any]] = None


class JobCreate(JobBase):
    """
    Job creation schema.
    Note: quote_id and po_number are intentionally omitted to support Dynamic Entry.
    """
    pass


class JobCreateDynamic(JobBase):
    """
    Dynamic Entry job creation - allows scheduling without PO.
    """
    schedule_immediately: bool = False
    machine_type: Optional[str] = None
    duration_hours: Optional[int] = None


class JobUpdate(BaseSchema):
    customer_name: Optional[str] = Field(None, min_length=1, max_length=255)
    customer_email: Optional[str] = None
    description: Optional[str] = None
    status: Optional[JobStatus] = None
    priority: Optional[int] = Field(None, ge=1, le=10)
    po_number: Optional[str] = None
    financial_hold: Optional[bool] = None
    financial_hold_reason: Optional[str] = None
    requested_delivery_date: Optional[datetime] = None
    estimated_delivery_date: Optional[datetime] = None
    extra_data: Optional[dict[str, Any]] = None


class JobResponse(JobBase):
    id: int
    job_number: str
    status: JobStatus
    quote_id: Optional[int] = None
    po_number: Optional[str] = None
    financial_hold: bool
    financial_hold_reason: Optional[str] = None
    estimated_delivery_date: Optional[datetime] = None
    actual_delivery_date: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime


# ============================================================================
# Quote Schemas
# ============================================================================

class QuoteBase(BaseSchema):
    quote_type: QuoteType
    material_cost: float = Field(default=0.0, ge=0)
    labor_cost: float = Field(default=0.0, ge=0)
    overhead_cost: float = Field(default=0.0, ge=0)
    margin_percentage: float = Field(default=0.20, ge=0, le=1)
    total_price: float = Field(..., ge=0)
    estimated_delivery_date: Optional[datetime] = None
    lead_time_days: Optional[int] = None


class QuoteCreate(QuoteBase):
    job_id: Optional[int] = None
    analysis_data: Optional[dict[str, Any]] = None


class QuoteResponse(QuoteBase):
    id: int
    quote_number: str
    job_id: Optional[int] = None
    is_accepted: bool
    accepted_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    analysis_data: Optional[dict[str, Any]] = None
    created_at: datetime


# ============================================================================
# Quote Options (Parallel Quoting Output)
# ============================================================================

class QuoteOption(BaseSchema):
    """Individual quote option from parallel quoting."""
    quote_type: QuoteType
    total_price: float
    estimated_delivery_date: datetime
    lead_time_days: int
    material_cost: float
    labor_cost: float
    overhead_cost: float
    details: str
    highlights: list[str]


class QuoteOptionsResponse(BaseSchema):
    """Response from parallel quoting engine."""
    job_id: Optional[int] = None
    customer_name: str
    request_summary: str
    options: list[QuoteOption]
    analysis: dict[str, Any]


# ============================================================================
# Production Slot Schemas
# ============================================================================

class ProductionSlotBase(BaseSchema):
    machine_id: int
    start_time: datetime
    end_time: datetime
    notes: Optional[str] = None


class ProductionSlotCreate(ProductionSlotBase):
    job_id: Optional[int] = None


class ProductionSlotResponse(ProductionSlotBase):
    id: int
    job_id: Optional[int] = None
    status: SlotStatus
    created_at: datetime


# ============================================================================
# Chat Schemas
# ============================================================================

class ChatMessageInput(BaseSchema):
    """Input for chat endpoint."""
    message: str = Field(..., min_length=1, max_length=10000)
    thread_id: Optional[str] = None


class ChatMessageResponse(BaseSchema):
    """Response from chat endpoint."""
    thread_id: str
    role: MessageRole
    content: str
    response_type: Optional[str] = None
    response_data: Optional[dict[str, Any]] = None
    created_at: datetime


# ============================================================================
# Generative UI Response Types
# ============================================================================

class UIResponseType(str, Enum):
    TEXT = "text"
    QUOTE_OPTIONS = "quote_options"
    JOB_STATUS = "job_status"
    SCHEDULE_VIEW = "schedule_view"
    INVENTORY_TABLE = "inventory_table"
    CHART = "chart"
    CONFIRMATION = "confirmation"
    ERROR = "error"


class GenerativeUIResponse(BaseSchema):
    """Structured response for Generative UI rendering."""
    type: UIResponseType
    message: str
    data: Optional[dict[str, Any]] = None
    actions: Optional[list[dict[str, str]]] = None


# ============================================================================
# Service Response Schemas (for Spoke services)
# ============================================================================

class StockCheckResult(BaseSchema):
    """Result from inventory check."""
    item_id: int
    item_name: str
    available: bool
    quantity_on_hand: int
    quantity_required: int
    shortage: int
    restock_date: Optional[datetime] = None
    vendor_lead_time_days: int


class SlotFindResult(BaseSchema):
    """Result from slot finding."""
    machine_id: int
    machine_name: str
    earliest_start: datetime
    earliest_end: datetime
    slot_available: bool
    alternative_slots: Optional[list[dict[str, Any]]] = None


class CostCalculation(BaseSchema):
    """Result from cost calculation."""
    material_cost: float
    labor_cost: float
    overhead_cost: float
    margin_amount: float
    total_price: float
    breakdown: dict[str, Any]
