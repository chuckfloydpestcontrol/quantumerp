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
HUB: Aluminum 6061 Sheet (AL6061-SH-1): 100 units @ $45.00/ea - In Stock
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
-> Job created automatically
```

**Directly (Dynamic Entry):**
```
"Create job for Acme Corp - 50 steel brackets"
-> Job created with financial hold (no PO yet)
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
- Bad: "Quote please"
- Good: "Quote for 50 aluminum brackets for Acme Corp"

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
