"""
Quantum HUB ERP - FastAPI Application

AI-native, Hub-and-Spoke ERP for manufacturing.
Features: Parallel Quoting, Dynamic Entry, Generative UI.
"""

import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import get_settings
from database import close_db, get_db, init_db
from hub import get_hub
from models import (
    ChatMessage,
    Customer,
    Item,
    Job,
    JobStatus,
    Machine,
    MessageRole,
    Quote,
    QuoteType,
)
from schemas import (
    ChatMessageInput,
    ChatMessageResponse,
    CustomerCreate,
    CustomerResponse,
    CustomerUpdate,
    GenerativeUIResponse,
    ItemCreate,
    ItemResponse,
    ItemUpdate,
    JobCreate,
    JobCreateDynamic,
    JobResponse,
    JobUpdate,
    MachineCreate,
    MachineResponse,
    QuoteResponse,
    UIResponseType,
)
from services import CostingService, CustomerService, InventoryService, JobService, SchedulingService

settings = get_settings()


# ============================================================================
# Application Lifecycle
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    await init_db()
    yield
    # Shutdown
    await close_db()


# ============================================================================
# OpenAPI Tags Metadata
# ============================================================================

tags_metadata = [
    {
        "name": "Chat",
        "description": "AI-powered chat interface - the primary way to interact with Quantum HUB. Natural language commands are interpreted and routed to appropriate workflows.",
    },
    {
        "name": "Jobs",
        "description": "Job lifecycle management. Jobs track manufacturing orders from quote to completion. Supports Dynamic Entry (schedule-first) workflow.",
    },
    {
        "name": "Inventory",
        "description": "Stock and materials management. Track quantities, reorder points, and vendor lead times.",
    },
    {
        "name": "Scheduling",
        "description": "Machine and production slot management. Find available capacity and schedule production.",
    },
    {
        "name": "Quoting",
        "description": "Cost estimation and pricing. Generate parallel quote options (Fastest, Cheapest, Balanced) using Fan-Out/Fan-In pattern.",
    },
    {
        "name": "Customers",
        "description": "Customer relationship management. Track customer details, payment terms, and credit limits.",
    },
    {
        "name": "System",
        "description": "Health checks, status monitoring, and development utilities.",
    },
]

app = FastAPI(
    title="Quantum HUB ERP",
    description="""
## AI-Native Hub-and-Spoke ERP for Manufacturing

Quantum HUB replaces linear workflows with parallel, agentic orchestration.

### Key Features
- **Parallel Quoting**: Fan-Out/Fan-In pattern generates Fastest, Cheapest, and Balanced options simultaneously
- **Dynamic Entry**: Schedule-first workflow allows production to proceed without a PO
- **Natural Language Interface**: Chat with the system using plain English

### Getting Started
1. Use the `/api/chat` endpoint to interact naturally
2. Or use individual REST endpoints for programmatic access
3. Visit `/api/seed` (POST) to populate demo data

### Quick Examples
- "I need a quote for 50 aluminum brackets"
- "list jobs"
- "show inventory"
- "add customer Acme Corp"
    """,
    version="1.0.0",
    lifespan=lifespan,
    openapi_tags=tags_metadata,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }


@app.get("/api/status")
async def system_status(db: AsyncSession = Depends(get_db)):
    """System status with component health."""
    # Check database
    try:
        result = await db.execute(select(Job).limit(1))
        db_status = "healthy"
    except Exception as e:
        db_status = f"error: {str(e)}"

    return {
        "status": "operational",
        "components": {
            "database": db_status,
            "hub": "ready",
            "services": "ready"
        },
        "timestamp": datetime.utcnow().isoformat()
    }


# ============================================================================
# Chat / Hub Endpoint (Primary Interface)
# ============================================================================

@app.post("/api/chat", response_model=ChatMessageResponse)
async def chat(
    input: ChatMessageInput,
    db: AsyncSession = Depends(get_db)
):
    """
    Primary chat endpoint for the Quantum HUB.

    This is the main interface for the prompt-driven ERP.
    User messages are processed by the LangGraph orchestrator.
    """
    thread_id = input.thread_id or str(uuid.uuid4())

    # Store user message
    user_message = ChatMessage(
        thread_id=thread_id,
        role=MessageRole.USER,
        content=input.message
    )
    db.add(user_message)
    await db.flush()  # Flush to persist before running hub

    # Run the hub with db session for conversation context
    hub = get_hub()
    result = await hub.run(input.message, thread_id, db=db)

    # Extract response
    messages = result.get("messages", [])
    response_content = ""
    if messages:
        last_message = messages[-1]
        response_content = last_message.content if hasattr(last_message, 'content') else str(last_message)

    response_type = result.get("response_type", "text")
    response_data = result.get("response_data")

    # Store assistant response
    assistant_message = ChatMessage(
        thread_id=thread_id,
        role=MessageRole.ASSISTANT,
        content=response_content,
        response_type=response_type,
        response_data=response_data
    )
    db.add(assistant_message)
    await db.commit()

    return ChatMessageResponse(
        thread_id=thread_id,
        role=MessageRole.ASSISTANT,
        content=response_content,
        response_type=response_type,
        response_data=response_data,
        created_at=datetime.utcnow()
    )


# ============================================================================
# Job Endpoints
# ============================================================================

@app.post("/api/jobs", response_model=JobResponse)
async def create_job(
    job_data: JobCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new job."""
    job_service = JobService(db)
    job = await job_service.create_job(
        customer_name=job_data.customer_name,
        description=job_data.description,
        customer_email=job_data.customer_email,
        priority=job_data.priority,
        requested_delivery_date=job_data.requested_delivery_date,
        extra_data=job_data.extra_data
    )
    await db.commit()
    return job


@app.post("/api/jobs/dynamic", response_model=JobResponse)
async def create_dynamic_job(
    job_data: JobCreateDynamic,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a job using Dynamic Entry (Schedule-First workflow).

    This creates a job in SCHEDULED status with financial hold,
    allowing production to proceed without a PO.
    """
    job_service = JobService(db)
    job = await job_service.create_scheduled_job(
        customer_name=job_data.customer_name,
        description=job_data.description,
        customer_email=job_data.customer_email,
        priority=job_data.priority,
        financial_hold_reason="Awaiting PO",
        extra_data=job_data.extra_data
    )

    # Optionally schedule immediately
    if job_data.schedule_immediately and job_data.machine_type and job_data.duration_hours:
        scheduling_service = SchedulingService(db)
        slot = await scheduling_service.find_slot(
            machine_type=job_data.machine_type,
            duration_hours=job_data.duration_hours
        )
        await scheduling_service.reserve_slot(
            machine_id=slot.machine_id,
            start_time=slot.earliest_start,
            end_time=slot.earliest_end,
            job_id=job.id,
            notes="Dynamic entry - auto-scheduled"
        )
        job.estimated_delivery_date = slot.earliest_end

    await db.commit()
    return job


@app.get("/api/jobs", response_model=list[JobResponse])
async def list_jobs(
    status: Optional[JobStatus] = None,
    db: AsyncSession = Depends(get_db)
):
    """List all jobs, optionally filtered by status."""
    job_service = JobService(db)

    if status:
        result = await db.execute(
            select(Job).where(Job.status == status)
        )
        jobs = list(result.scalars().all())
    else:
        jobs = await job_service.get_active_jobs()

    return jobs


@app.get("/api/jobs/{job_id}", response_model=JobResponse)
async def get_job(job_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific job by ID."""
    job_service = JobService(db)
    job = await job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.patch("/api/jobs/{job_id}", response_model=JobResponse)
async def update_job(
    job_id: int,
    update_data: JobUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a job."""
    job_service = JobService(db)
    job = await job_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(job, field, value)

    await db.commit()
    return job


@app.post("/api/jobs/{job_id}/attach-po")
async def attach_po(
    job_id: int,
    po_number: str,
    db: AsyncSession = Depends(get_db)
):
    """Attach a PO number to a job and clear financial hold."""
    job_service = JobService(db)
    job = await job_service.attach_po(job_id, po_number)
    await db.commit()
    return {
        "message": f"PO {po_number} attached to job {job.job_number}",
        "job_id": job.id,
        "financial_hold": job.financial_hold
    }


@app.post("/api/jobs/{job_id}/accept-quote")
async def accept_quote(
    job_id: int,
    quote_type: QuoteType,
    db: AsyncSession = Depends(get_db)
):
    """Accept a quote option and schedule the job."""
    job_service = JobService(db)
    job = await job_service.accept_quote(job_id)
    await db.commit()
    return {
        "message": f"Quote accepted for job {job.job_number}",
        "job_id": job.id,
        "status": job.status.value
    }


# ============================================================================
# Inventory Endpoints
# ============================================================================

@app.post("/api/items", response_model=ItemResponse)
async def create_item(
    item_data: ItemCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new inventory item."""
    inventory_service = InventoryService(db)
    item = await inventory_service.create_item(**item_data.model_dump())
    await db.commit()
    return item


@app.get("/api/items", response_model=list[ItemResponse])
async def list_items(
    category: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """List inventory items."""
    if category:
        inventory_service = InventoryService(db)
        items = await inventory_service.get_item_by_category(category)
    else:
        result = await db.execute(select(Item))
        items = list(result.scalars().all())
    return items


@app.get("/api/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific item."""
    result = await db.execute(select(Item).where(Item.id == item_id))
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item


@app.get("/api/items/check-stock/{item_id}")
async def check_stock(
    item_id: int,
    quantity: int = 1,
    db: AsyncSession = Depends(get_db)
):
    """Check stock availability for an item."""
    inventory_service = InventoryService(db)
    try:
        result = await inventory_service.check_stock(item_id, quantity)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/api/inventory/low-stock")
async def get_low_stock(db: AsyncSession = Depends(get_db)):
    """Get items below reorder point."""
    inventory_service = InventoryService(db)
    items = await inventory_service.get_low_stock_items()
    return [ItemResponse.model_validate(item) for item in items]


# ============================================================================
# Machine & Scheduling Endpoints
# ============================================================================

@app.post("/api/machines", response_model=MachineResponse)
async def create_machine(
    machine_data: MachineCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new machine."""
    scheduling_service = SchedulingService(db)
    machine = await scheduling_service.create_machine(**machine_data.model_dump())
    await db.commit()
    return machine


@app.get("/api/machines", response_model=list[MachineResponse])
async def list_machines(db: AsyncSession = Depends(get_db)):
    """List all machines."""
    result = await db.execute(select(Machine))
    return list(result.scalars().all())


@app.get("/api/schedule")
async def get_schedule(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Get production schedule for all machines (Gantt view data)."""
    scheduling_service = SchedulingService(db)

    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None

    schedules = await scheduling_service.get_all_schedules(start, end)
    return {
        "type": "schedule_view",
        "data": schedules
    }


@app.get("/api/schedule/find-slot")
async def find_slot(
    machine_type: str,
    duration_hours: int,
    db: AsyncSession = Depends(get_db)
):
    """Find the next available slot for a machine type."""
    scheduling_service = SchedulingService(db)
    try:
        result = await scheduling_service.find_slot(machine_type, duration_hours)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Quoting Endpoints
# ============================================================================

@app.post("/api/quotes/calculate")
async def calculate_quote(
    bom: list[dict],
    labor_hours: float,
    machine_id: Optional[int] = None,
    expedited: bool = False,
    db: AsyncSession = Depends(get_db)
):
    """Calculate a quote for given BOM and labor."""
    costing_service = CostingService(db)
    result = await costing_service.calculate_quote(
        bom=bom,
        labor_hours=labor_hours,
        machine_id=machine_id,
        expedited=expedited
    )
    return result


@app.post("/api/quotes/parallel")
async def parallel_quote(
    bom: list[dict],
    labor_hours: float,
    machine_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate parallel quote options (Fastest, Cheapest, Balanced).

    This endpoint demonstrates the core Parallel Quoting feature.
    """
    costing_service = CostingService(db)
    scheduling_service = SchedulingService(db)

    # Get scheduling info for lead time
    try:
        slot = await scheduling_service.find_slot("cnc", int(labor_hours))
        lead_time = (slot.earliest_start - datetime.utcnow()).days
    except:
        lead_time = 7

    options = await costing_service.calculate_quote_options(
        bom=bom,
        labor_hours=labor_hours,
        machine_id=machine_id,
        current_lead_time_days=lead_time
    )

    return {
        "type": "quote_options",
        "data": options
    }


@app.get("/api/quotes", response_model=list[QuoteResponse])
async def list_quotes(db: AsyncSession = Depends(get_db)):
    """List all quotes."""
    result = await db.execute(select(Quote))
    return list(result.scalars().all())


# ============================================================================
# Customer Endpoints
# ============================================================================

@app.post("/api/customers", response_model=CustomerResponse)
async def create_customer(
    customer_data: CustomerCreate,
    db: AsyncSession = Depends(get_db)
):
    """Create a new customer."""
    customer_service = CustomerService(db)
    customer = await customer_service.create_customer(
        name=customer_data.name,
        email=customer_data.email,
        phone=customer_data.phone,
        address=customer_data.address,
        billing_address=customer_data.billing_address,
        active=customer_data.active,
        notes=customer_data.notes,
        credit_limit=customer_data.credit_limit,
        payment_terms_days=customer_data.payment_terms_days
    )
    await db.commit()
    return customer


@app.get("/api/customers", response_model=list[CustomerResponse])
async def list_customers(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db)
):
    """List all customers."""
    customer_service = CustomerService(db)
    customers = await customer_service.list_customers(active_only=active_only)
    return customers


@app.get("/api/customers/search", response_model=list[CustomerResponse])
async def search_customers(
    query: str,
    db: AsyncSession = Depends(get_db)
):
    """Search customers by name or email."""
    customer_service = CustomerService(db)
    customers = await customer_service.search_customers(query)
    return customers


@app.get("/api/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific customer by ID."""
    customer_service = CustomerService(db)
    customer = await customer_service.get_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    return customer


@app.patch("/api/customers/{customer_id}", response_model=CustomerResponse)
async def update_customer(
    customer_id: int,
    update_data: CustomerUpdate,
    db: AsyncSession = Depends(get_db)
):
    """Update a customer."""
    customer_service = CustomerService(db)
    customer = await customer_service.update_customer(
        customer_id,
        **update_data.model_dump(exclude_unset=True)
    )
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return customer


@app.delete("/api/customers/{customer_id}")
async def deactivate_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Soft-delete a customer by setting active=False."""
    customer_service = CustomerService(db)
    customer = await customer_service.deactivate_customer(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")
    await db.commit()
    return {"message": f"Customer {customer.name} has been deactivated", "customer_id": customer.id}


# ============================================================================
# WebSocket for Real-time Updates
# ============================================================================

class ConnectionManager:
    """Manage WebSocket connections."""

    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except:
                pass


manager = ConnectionManager()


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time updates."""
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Echo or process WebSocket messages
            await websocket.send_json({
                "type": "ack",
                "message": f"Received: {data}"
            })
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ============================================================================
# Seed Data Endpoint (Development)
# ============================================================================

@app.post("/api/seed")
async def seed_data(db: AsyncSession = Depends(get_db)):
    """Seed database with demo data (development only)."""
    if not settings.debug:
        raise HTTPException(status_code=403, detail="Only available in debug mode")

    # Seed machines
    machines_data = [
        {"name": "CNC-Mill-1", "machine_type": "cnc", "hourly_rate": 75.0,
         "capabilities": {"materials": ["aluminum", "steel"], "max_size": "24x24"}},
        {"name": "CNC-Mill-2", "machine_type": "cnc", "hourly_rate": 75.0,
         "capabilities": {"materials": ["aluminum", "steel"], "max_size": "24x24"}},
        {"name": "5-Axis-1", "machine_type": "5-axis", "hourly_rate": 125.0,
         "capabilities": {"materials": ["aluminum", "titanium"], "complex": True}},
        {"name": "Lathe-1", "machine_type": "lathe", "hourly_rate": 60.0,
         "capabilities": {"materials": ["steel", "brass"]}},
    ]

    for m in machines_data:
        machine = Machine(**m)
        db.add(machine)

    # Seed inventory items
    items_data = [
        {"name": "Aluminum 6061 Sheet", "sku": "AL6061-SH-1", "cost_per_unit": 45.00,
         "quantity_on_hand": 100, "vendor_lead_time_days": 5, "category": "raw_material"},
        {"name": "Steel 1018 Bar", "sku": "ST1018-BR-1", "cost_per_unit": 32.00,
         "quantity_on_hand": 75, "vendor_lead_time_days": 3, "category": "raw_material"},
        {"name": "Titanium Grade 5", "sku": "TI-GR5-1", "cost_per_unit": 180.00,
         "quantity_on_hand": 20, "vendor_lead_time_days": 14, "category": "raw_material"},
        {"name": "Brass C360", "sku": "BR-C360-1", "cost_per_unit": 55.00,
         "quantity_on_hand": 50, "vendor_lead_time_days": 7, "category": "raw_material"},
        {"name": "M5 Socket Cap Screws (100)", "sku": "HW-M5SCS-100", "cost_per_unit": 12.00,
         "quantity_on_hand": 500, "vendor_lead_time_days": 2, "category": "hardware"},
    ]

    for i in items_data:
        item = Item(**i)
        db.add(item)

    # Seed customers
    customers_data = [
        {"name": "Acme Manufacturing", "email": "orders@acmemfg.com", "phone": "555-100-1000",
         "address": "123 Industrial Blvd, Detroit, MI 48201", "payment_terms_days": 30},
        {"name": "Precision Parts Inc", "email": "purchasing@precisionparts.com", "phone": "555-200-2000",
         "address": "456 Tech Park Dr, Austin, TX 78701", "credit_limit": 50000.00, "payment_terms_days": 45},
        {"name": "Aerospace Dynamics", "email": "procurement@aerodyn.com", "phone": "555-300-3000",
         "address": "789 Aviation Way, Seattle, WA 98101", "credit_limit": 100000.00, "payment_terms_days": 60},
        {"name": "AutoMotive Solutions", "email": "supply@automotivesol.com", "phone": "555-400-4000",
         "address": "321 Motor Lane, Dearborn, MI 48124", "payment_terms_days": 30},
    ]

    for c in customers_data:
        customer = Customer(**c)
        db.add(customer)

    await db.commit()

    return {
        "message": "Database seeded with demo data",
        "machines": len(machines_data),
        "items": len(items_data),
        "customers": len(customers_data)
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=settings.host, port=settings.port)
