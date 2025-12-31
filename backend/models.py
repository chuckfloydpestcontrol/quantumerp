"""SQLAlchemy 2.0 declarative models for Quantum HUB ERP."""

import enum
from datetime import datetime
from typing import Optional
from uuid import uuid4

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


# ============================================================================
# Enums
# ============================================================================

class JobStatus(str, enum.Enum):
    """Job lifecycle status."""
    DRAFT = "draft"
    QUOTED = "quoted"
    SCHEDULED = "scheduled"
    FINANCIAL_HOLD = "financial_hold"
    IN_PRODUCTION = "in_production"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class QuoteType(str, enum.Enum):
    """Quote optimization type."""
    FASTEST = "fastest"
    CHEAPEST = "cheapest"
    BALANCED = "balanced"


class SlotStatus(str, enum.Enum):
    """Production slot status."""
    AVAILABLE = "available"
    RESERVED = "reserved"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"


class MessageRole(str, enum.Enum):
    """Chat message role."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


# ============================================================================
# Inventory Module Models
# ============================================================================

class Item(Base):
    """Inventory item model."""
    __tablename__ = "items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sku: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    reorder_point: Mapped[int] = mapped_column(Integer, default=10)
    cost_per_unit: Mapped[float] = mapped_column(Float, nullable=False)
    vendor_lead_time_days: Mapped[int] = mapped_column(Integer, default=7)
    vendor_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    specifications: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Vector embedding for semantic search
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    bom_items: Mapped[list["BOMItem"]] = relationship(back_populates="item")


# ============================================================================
# Scheduling Module Models
# ============================================================================

class Machine(Base):
    """Manufacturing machine/resource model."""
    __tablename__ = "machines"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    machine_type: Mapped[str] = mapped_column(String(100), nullable=False)
    hourly_rate: Mapped[float] = mapped_column(Float, nullable=False)
    capabilities: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="operational")
    location: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    production_slots: Mapped[list["ProductionSlot"]] = relationship(back_populates="machine")


class ProductionSlot(Base):
    """Production schedule slot model."""
    __tablename__ = "production_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    machine_id: Mapped[int] = mapped_column(ForeignKey("machines.id"), nullable=False)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jobs.id"), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[SlotStatus] = mapped_column(
        Enum(SlotStatus), default=SlotStatus.AVAILABLE
    )
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    machine: Mapped["Machine"] = relationship(back_populates="production_slots")
    job: Mapped[Optional["Job"]] = relationship(back_populates="production_slots")


# ============================================================================
# Job Module Models (Central Entity)
# ============================================================================

class Job(Base):
    """
    Central Job entity tracking the lifecycle of an order.

    CRITICAL: quote_id and po_number are NULLABLE to support Dynamic Entry.
    This allows creating jobs in 'SCHEDULED' status without financial documents.
    """
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    customer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    customer_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status tracking
    status: Mapped[JobStatus] = mapped_column(
        Enum(JobStatus), default=JobStatus.DRAFT
    )
    priority: Mapped[int] = mapped_column(Integer, default=5)  # 1=highest, 10=lowest

    # NULLABLE foreign keys for Dynamic Entry support
    quote_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("quotes.id"), nullable=True
    )
    po_number: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Financial hold flag for Schedule-First workflow
    financial_hold: Mapped[bool] = mapped_column(Boolean, default=False)
    financial_hold_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Delivery
    requested_delivery_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    estimated_delivery_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_delivery_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Metadata
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    quote: Mapped[Optional["Quote"]] = relationship(foreign_keys=[quote_id])
    production_slots: Mapped[list["ProductionSlot"]] = relationship(back_populates="job")
    bom_items: Mapped[list["BOMItem"]] = relationship(back_populates="job")


# ============================================================================
# Quoting Module Models
# ============================================================================

class Quote(Base):
    """Quote/estimate model."""
    __tablename__ = "quotes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    quote_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jobs.id"), nullable=True)

    # Quote type from parallel quoting
    quote_type: Mapped[QuoteType] = mapped_column(
        Enum(QuoteType), default=QuoteType.BALANCED
    )

    # Pricing
    material_cost: Mapped[float] = mapped_column(Float, default=0.0)
    labor_cost: Mapped[float] = mapped_column(Float, default=0.0)
    overhead_cost: Mapped[float] = mapped_column(Float, default=0.0)
    margin_percentage: Mapped[float] = mapped_column(Float, default=0.20)
    total_price: Mapped[float] = mapped_column(Float, nullable=False)

    # Delivery estimate
    estimated_delivery_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    lead_time_days: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Status
    is_accepted: Mapped[bool] = mapped_column(Boolean, default=False)
    accepted_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Analysis data from parallel quoting
    analysis_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationship removed to avoid circular FK complexity
    # Access job via job_id foreign key directly


class BOMItem(Base):
    """Bill of Materials item model."""
    __tablename__ = "bom_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("jobs.id"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("items.id"), nullable=False)
    quantity_required: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_cost: Mapped[float] = mapped_column(Float, nullable=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    job: Mapped["Job"] = relationship(back_populates="bom_items")
    item: Mapped["Item"] = relationship(back_populates="bom_items")


# ============================================================================
# Hub Module Models (LangGraph State Persistence)
# ============================================================================

class ConversationState(Base):
    """LangGraph conversation state persistence."""
    __tablename__ = "conversation_states"

    thread_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    checkpoint: Mapped[dict] = mapped_column(JSONB, nullable=False)
    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    parent_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ChatMessage(Base):
    """Chat message history for audit and context."""
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    thread_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[MessageRole] = mapped_column(Enum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # For generative UI responses
    response_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    response_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Vector embedding for semantic search
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ============================================================================
# Document Storage (Unified Data Fabric)
# ============================================================================

class Document(Base):
    """Document storage for unstructured data (PDFs, drawings, etc.)."""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str] = mapped_column(String(512), nullable=False)
    file_type: Mapped[str] = mapped_column(String(50), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)

    # Related entity
    job_id: Mapped[Optional[int]] = mapped_column(ForeignKey("jobs.id"), nullable=True)

    # Extracted content for search
    content_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Vector embedding for semantic search
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)

    extra_data: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
