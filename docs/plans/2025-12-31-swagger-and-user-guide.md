# Swagger Enhancement & Operator Guide Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enhance Swagger UI with detailed documentation and create a comprehensive operator guide with in-app help.

**Architecture:** Add OpenAPI metadata (tags, descriptions, examples) to FastAPI app, add HELP intent to LangGraph hub for in-app assistance, and create a standalone markdown user guide.

**Tech Stack:** FastAPI OpenAPI, LangGraph, Markdown

---

## Task 1: Add OpenAPI Tags Metadata

**Files:**
- Modify: `backend/main.py:70-75`

**Step 1: Add tags_metadata before FastAPI app initialization**

Insert after line 68 (after `close_db` import section), before the FastAPI app:

```python
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
```

**Step 2: Update FastAPI app initialization to use tags**

Change the FastAPI initialization to:

```python
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
```

**Step 3: Verify syntax**

Run: `cd /home/erp/app/backend && python -c "import main; print('OK')"`
Expected: `OK`

**Step 4: Commit**

```bash
git add backend/main.py
git commit -m "feat: add OpenAPI tags metadata for Swagger grouping"
```

---

## Task 2: Add Tags to All Endpoints

**Files:**
- Modify: `backend/main.py` (multiple sections)

**Step 1: Add tags to Health & Status endpoints (lines ~91-130)**

Update each endpoint to include `tags=["System"]`:

```python
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    ...

@app.get("/api/status", tags=["System"])
async def system_status():
    """System status with component health."""
    ...
```

**Step 2: Add tags to Chat endpoint**

```python
@app.post("/api/chat", response_model=ChatMessageResponse, tags=["Chat"])
async def chat(
    message: ChatMessageInput,
    db: AsyncSession = Depends(get_db)
):
    """
    Primary chat endpoint for the Quantum HUB.

    This is the main interface for the prompt-driven ERP.
    User messages are processed by the LangGraph orchestrator.

    **Example messages:**
    - "I need a quote for 50 aluminum brackets"
    - "list jobs"
    - "show inventory"
    - "create job for Acme Corp"
    - "help" (shows available commands)
    """
    ...
```

**Step 3: Add tags to Jobs endpoints**

Add `tags=["Jobs"]` to all `/api/jobs*` endpoints:
- `POST /api/jobs`
- `GET /api/jobs`
- `POST /api/jobs/dynamic`
- `GET /api/jobs/{job_id}`
- `PATCH /api/jobs/{job_id}`
- `POST /api/jobs/{job_id}/attach-po`
- `POST /api/jobs/{job_id}/accept-quote`

**Step 4: Add tags to Inventory endpoints**

Add `tags=["Inventory"]` to all `/api/items*` and `/api/inventory*` endpoints:
- `POST /api/items`
- `GET /api/items`
- `GET /api/items/{item_id}`
- `GET /api/items/check-stock/{item_id}`
- `GET /api/inventory/low-stock`

**Step 5: Add tags to Scheduling endpoints**

Add `tags=["Scheduling"]` to:
- `POST /api/machines`
- `GET /api/machines`
- `GET /api/schedule`
- `GET /api/schedule/find-slot`

**Step 6: Add tags to Quoting endpoints**

Add `tags=["Quoting"]` to:
- `POST /api/quotes/calculate`
- `POST /api/quotes/parallel`
- `GET /api/quotes`

**Step 7: Add tags to Customer endpoints**

Add `tags=["Customers"]` to all `/api/customers*` endpoints:
- `POST /api/customers`
- `GET /api/customers`
- `GET /api/customers/search`
- `GET /api/customers/{customer_id}`
- `PATCH /api/customers/{customer_id}`
- `DELETE /api/customers/{customer_id}`

**Step 8: Add tags to Seed endpoint**

Add `tags=["System"]` to:
- `POST /api/seed`

**Step 9: Verify Swagger loads**

Run: `curl -s http://localhost:8000/openapi.json | python -c "import sys,json; d=json.load(sys.stdin); print('Tags:', [t['name'] for t in d.get('tags',[])])"`
Expected: `Tags: ['Chat', 'Jobs', 'Inventory', 'Scheduling', 'Quoting', 'Customers', 'System']`

**Step 10: Commit**

```bash
git add backend/main.py
git commit -m "feat: add OpenAPI tags to all endpoints"
```

---

## Task 3: Add HELP Intent to Hub

**Files:**
- Modify: `backend/hub.py:102-202` (SUPERVISOR_SYSTEM_PROMPT)
- Modify: `backend/hub.py:251-341` (_build_graph)
- Modify: `backend/hub.py:379-451` (_route_from_supervisor)
- Add new method: `_help_node`

**Step 1: Add HELP to SUPERVISOR_SYSTEM_PROMPT**

In the SUPERVISOR_SYSTEM_PROMPT (around line 150), add after GENERAL_QUERY:

```python
- HELP: User wants help or wants to know what commands are available (e.g., "help", "what can you do?", "commands")
```

Also update the JSON response intent list to include `HELP`.

**Step 2: Add help node to _build_graph**

After line 298 (after financial_hold_report node), add:

```python
        # Add node - Help
        workflow.add_node("help", self._help_node)
```

**Step 3: Add help route to conditional edges**

In the conditional edges dict (around line 336), add:

```python
                "help": "help",
```

**Step 4: Add help edge to END**

After line 374, add:

```python
        workflow.add_edge("help", END)
```

**Step 5: Add help route in _route_from_supervisor**

After the FINANCIAL_HOLD_REPORT check (around line 445), add:

```python
        # Help
        elif intent == "HELP":
            return "help"
```

**Step 6: Add _help_node method**

Add this method to the QuantumHub class (after _financial_hold_report_node):

```python
    async def _help_node(self, state: AgentState) -> dict:
        """Help Node - Shows available commands and examples."""
        help_text = """**Quantum HUB Quick Help**

**Quoting:**
- "I need a quote for 10 aluminum brackets"
- "list quotes" / "view quote Q-20251231-0001"
- "accept the balanced option"

**Jobs:**
- "create job for Acme Corp - 50 steel brackets"
- "list jobs" / "show job J-20251231-0001"
- "update job priority to 8"
- "attach PO-12345 to job"

**Inventory:**
- "show inventory" / "check stock for aluminum"
- "what's running low?"
- "reorder titanium" / "add 50 units of steel"

**Customers:**
- "list customers" / "add customer Widget Inc"

**Machines & Scheduling:**
- "list machines" / "add machine Laser-2 at $150/hr"
- "show schedule" / "find slot for 4 hours on CNC"

**Reports:**
- "show jobs on financial hold"
- "machine utilization"

Type naturally - I'll understand what you need!"""

        return {
            "messages": [AIMessage(content=help_text)],
            "response_type": "help",
            "response_data": {"topic": "general_help"}
        }
```

**Step 7: Test HELP intent**

Run:
```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "help"}' | python -c "import sys,json; print(json.load(sys.stdin)['content'][:50])"
```
Expected: `**Quantum HUB Quick Help**` (or similar)

**Step 8: Commit**

```bash
git add backend/hub.py
git commit -m "feat: add HELP intent for in-app quick reference"
```

---

## Task 4: Create Operator User Guide

**Files:**
- Create: `docs/user-guide.md`

**Step 1: Create the user guide**

Create `/home/erp/app/docs/user-guide.md` with full content (see below).

**Step 2: Verify file exists**

Run: `head -5 /home/erp/app/docs/user-guide.md`
Expected: First 5 lines of the guide

**Step 3: Commit**

```bash
git add docs/user-guide.md
git commit -m "docs: add comprehensive operator user guide"
```

---

## Task 5: Restart Backend and Final Verification

**Step 1: Restart backend**

Run: `sg docker -c 'docker compose restart backend'`

**Step 2: Wait for startup**

Run: `sleep 5`

**Step 3: Verify Swagger UI loads with tags**

Run: `curl -s http://localhost:8000/docs | grep -o 'Swagger UI' | head -1`
Expected: `Swagger UI`

**Step 4: Verify HELP intent works**

Run:
```bash
curl -s -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "what can you do?"}' | python -m json.tool | head -10
```
Expected: Response with help content

**Step 5: Final commit and push**

```bash
git add -A
git commit -m "feat: complete Swagger docs and operator guide implementation"
git push origin feature/mvp-enhancements
```

---

## User Guide Content

The user guide (`docs/user-guide.md`) should contain:

```markdown
# Quantum HUB ERP - Operator Guide

Welcome to Quantum HUB, an AI-powered ERP system designed for manufacturing operations. This guide will help you use the system effectively for daily tasks.

## Table of Contents

1. [Getting Started](#getting-started)
2. [The Chat Interface](#the-chat-interface)
3. [Quoting Workflow](#quoting-workflow)
4. [Job Management](#job-management)
5. [Inventory Operations](#inventory-operations)
6. [Customers & Machines](#customers--machines)
7. [Quick Reference](#quick-reference)
8. [Troubleshooting](#troubleshooting)

---

## Getting Started

### What is Quantum HUB?

Quantum HUB is an AI-native ERP system that understands natural language. Instead of clicking through menus, you simply tell it what you need:

- "I need a quote for 50 aluminum brackets"
- "Show me all active jobs"
- "What inventory is running low?"

The system interprets your request, gathers information from multiple sources simultaneously, and presents clear options.

### Key Concepts

| Term | Meaning |
|------|---------|
| **Job** | A manufacturing order that tracks work from quote to completion |
| **Quote** | A price estimate with three options: Fastest, Cheapest, Balanced |
| **Dynamic Entry** | Starting a job before receiving a PO (schedule-first workflow) |
| **Financial Hold** | A job waiting for a PO number before proceeding |

### Your First Interaction

1. Open the Quantum HUB chat interface
2. Type: `help`
3. You'll see a list of everything you can do

---

## The Chat Interface

The chat interface is your primary tool. It understands natural language, so you don't need to memorize exact commands.

### Tips for Best Results

- **Be specific**: "Quote for 50 aluminum 6061 brackets" works better than "I need a quote"
- **Include quantities**: Always mention how many items when relevant
- **Use names**: Reference jobs, customers, and items by name or number

### Example Conversations

**Getting a quote:**
```
You: I need a quote for 100 steel mounting plates for Acme Corp
HUB: Here are your quote options:
     - FASTEST: $2,450 - Delivery in 5 days
     - CHEAPEST: $1,890 - Delivery in 12 days
     - BALANCED: $2,100 - Delivery in 8 days (Recommended)
```

**Checking inventory:**
```
You: What's our aluminum stock looking like?
HUB: Aluminum 6061 Sheet (AL6061-SH-1): 100 units @ $45.00/ea ✓ In Stock
```

---

## Quoting Workflow

### Requesting a Quote

To get a quote, tell the system what you need to manufacture:

```
"I need a quote for 50 aluminum brackets"
"Quote for Precision Parts - 200 steel gears, need it by January 15"
"How much to make 25 titanium housings?"
```

### Understanding Quote Options

Every quote gives you three options:

| Option | Best For |
|--------|----------|
| **Fastest** | Rush orders, urgent customer needs |
| **Cheapest** | Cost-sensitive orders, flexible timelines |
| **Balanced** | Most orders - optimal price/time trade-off |

### Accepting a Quote

Once you've reviewed the options:

```
"Accept the balanced option"
"Go with the fastest quote"
"Accept cheapest for job J-20251231-0001"
```

### Quote Expiration

Quotes are valid for **30 days**. After that, you'll need to request a new quote as material costs and availability may have changed.

---

## Job Management

### Creating Jobs

**From a quote:**
```
"Accept the balanced option"
→ Job created automatically
```

**Directly (Dynamic Entry):**
```
"Create job for Acme Corp - 50 steel brackets"
→ Job created with financial hold (no PO yet)
```

### Checking Job Status

```
"List jobs"
"Show active jobs"
"What's the status of job J-20251231-0001?"
"Show jobs for Acme Corp"
```

### Job Statuses Explained

| Status | Meaning |
|--------|---------|
| **Draft** | Job created, not yet quoted |
| **Quoted** | Quote generated, awaiting acceptance |
| **Scheduled** | Quote accepted, production scheduled |
| **Financial Hold** | Scheduled but waiting for PO |
| **In Production** | Currently being manufactured |
| **Completed** | Finished and delivered |
| **Cancelled** | Job was cancelled |

### Updating Jobs

```
"Update job J-20251231-0001 priority to 1"
"Change delivery date for job to January 20"
"Start production on job J-20251231-0001"
"Complete job J-20251231-0001"
```

### Dynamic Entry (Schedule-First)

When a customer needs something urgently but hasn't sent a PO yet:

1. Create the job: `"Create job for Acme Corp - 50 brackets, urgent"`
2. The job goes on **financial hold**
3. Production can be scheduled and prepared
4. When PO arrives: `"Attach PO-12345 to job J-20251231-0001"`
5. Financial hold is released

---

## Inventory Operations

### Checking Stock

```
"Show inventory"
"Check stock for aluminum"
"How much titanium do we have?"
"What's the stock level for SKU AL6061-SH-1?"
```

### Low Stock Alerts

```
"What's running low?"
"Show low stock items"
"Any items below reorder point?"
```

### Reordering

```
"Reorder aluminum 6061"
"Restock titanium - need 50 units"
"Place order for steel bars"
```

### Adding Inventory Items

```
"Add new item Copper Wire, SKU CU-001, $25 per unit"
"Add inventory: Stainless Steel Rod, SKU SS-ROD-1, category raw_material, $40/unit"
```

### Adjusting Stock

```
"Add 50 units of aluminum"
"Received shipment: 100 steel bars"
"Remove 10 units of titanium (damaged)"
```

---

## Customers & Machines

### Managing Customers

**List customers:**
```
"Show customers"
"List all customers"
```

**Add a customer:**
```
"Add customer Widget Corp, email orders@widget.com"
"Add customer Aerospace Dynamics, phone 555-300-3000"
```

### Managing Machines

**List machines:**
```
"Show machines"
"List equipment"
```

**Add a machine:**
```
"Add machine CNC-Mill-3, type cnc, $85 per hour"
"Add laser cutter Laser-2 at $200/hour"
```

**Check utilization:**
```
"Machine utilization"
"How busy are the CNC machines?"
```

### Viewing the Schedule

```
"Show schedule"
"What's on the production schedule this week?"
"Find a 4-hour slot on a CNC machine"
```

---

## Quick Reference

### Common Commands

| Task | Say This |
|------|----------|
| Get help | `help` |
| Request quote | `quote for [quantity] [item] for [customer]` |
| Accept quote | `accept [fastest/cheapest/balanced] option` |
| List jobs | `list jobs` or `show jobs` |
| Job details | `show job [number]` |
| Check inventory | `show inventory` or `check stock for [item]` |
| Low stock | `what's running low?` |
| Add customer | `add customer [name], email [email]` |
| List machines | `list machines` |

### Job Number Format

Jobs are numbered: `J-YYYYMMDD-NNNN`
- Example: `J-20251231-0001` (first job on Dec 31, 2025)

### Quote Number Format

Quotes are numbered: `Q-YYYYMMDD-NNNN`
- Example: `Q-20251231-0001`

---

## Troubleshooting

### "I didn't understand that"

Try rephrasing with more specific details:
- ❌ "Quote please"
- ✓ "Quote for 50 aluminum brackets for Acme Corp"

### Job stuck on Financial Hold

Attach a PO number:
```
"Attach PO-12345 to job J-20251231-0001"
```

### Can't find a job

Search by customer or description:
```
"Search jobs for Acme"
"Show jobs with brackets"
```

### Quote expired

Request a new quote - prices and availability may have changed:
```
"New quote for job J-20251231-0001"
```

---

## Getting More Help

- Type `help` anytime for quick reference
- Contact your system administrator for technical issues
- Check the API documentation at `/docs` for developer access
```
