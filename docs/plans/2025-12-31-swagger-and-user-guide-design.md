# Design: Swagger Documentation & Operator Guide

**Date:** 2025-12-31
**Status:** Approved
**Branch:** `feature/mvp-enhancements`

---

## Overview

Enhance Quantum HUB ERP with comprehensive documentation:
1. Enhanced Swagger UI with detailed descriptions and examples
2. Standalone operator guide for daily manufacturing workflows
3. In-app help accessible via chat

## Part 1: Enhanced Swagger Documentation

### Approach
Add OpenAPI metadata directly to FastAPI endpoints in `backend/main.py`.

### Changes

**1. Add `tags_metadata` for logical grouping:**
- `Chat` - AI hub interface
- `Jobs` - Job lifecycle management
- `Inventory` - Stock and items
- `Scheduling` - Machines and production slots
- `Quoting` - Cost estimation and pricing
- `Customers` - Customer management
- `System` - Health, status, seed

**2. Enhance each endpoint with:**
- Detailed `description` explaining purpose and usage
- Clear `summary` for the endpoint list
- `response_model_json_schema_extra` with realistic examples
- `openapi_examples` for request bodies where applicable

### Result
The `/docs` page becomes a complete, self-documenting API reference with try-it-out examples.

---

## Part 2: Standalone User Guide

### Location
`docs/user-guide.md`

### Structure

```
# Quantum HUB ERP - Operator Guide

1. Getting Started
   - What is Quantum HUB?
   - The Chat Interface (your main tool)
   - Quick Start: Your first quote

2. Quoting Workflow
   - Requesting a quote ("I need a quote for...")
   - Understanding quote options (Fastest/Cheapest/Balanced)
   - Accepting a quote
   - Quote expiration (30-day validity)

3. Job Management
   - Creating jobs from quotes
   - Dynamic Entry: Schedule-first workflow (no PO yet)
   - Tracking job status
   - Updating job priority
   - Attaching a PO to clear financial hold

4. Inventory Operations
   - Checking current stock
   - Viewing low-stock alerts
   - Reordering items
   - Adding new inventory items

5. Customers & Machines
   - Adding/listing customers
   - Adding/listing machines

6. Quick Reference
   - Common chat commands table
   - Job status meanings
   - Troubleshooting tips
```

### Tone
Conversational, task-focused. Each section answers "How do I...?" with concrete examples.

---

## Part 3: In-App Help via Chat

### Implementation
Add a `HELP` intent to the LangGraph hub in `backend/hub.py`.

### Trigger Phrases
- `help`
- `how do I...`
- `what can you do?`
- `commands`

### Response Format
```
**Quantum HUB Quick Help**

**Quoting:**
- "I need a quote for 10 aluminum brackets"
- "list quotes" / "view quote Q-001"

**Jobs:**
- "create job for Acme Corp"
- "list jobs" / "show job J-001"
- "update job J-001 priority to 8"

**Inventory:**
- "show inventory" / "check stock for aluminum"
- "what's running low?" / "reorder titanium"

**Customers & Machines:**
- "list customers" / "add customer Widget Inc"
- "list machines" / "add machine Laser-2 at $150/hr"

Type any of these or ask naturally - I'll figure out what you need!
```

### Changes to `backend/hub.py`
- Add `HELP` to intent classification
- Add keyword matching for help phrases
- Add `handle_help` node with formatted response
- Wire into graph routing

---

## Files to Modify

| File | Changes |
|------|---------|
| `backend/main.py` | Add tags_metadata, enhance endpoint descriptions and examples |
| `backend/hub.py` | Add HELP intent and handler |
| `docs/user-guide.md` | NEW - Comprehensive operator guide |

---

## Implementation Order

1. Enhance Swagger docs in `main.py`
2. Add HELP intent to `hub.py`
3. Create `docs/user-guide.md`
4. Test all three components
5. Commit and push
