# Quantum HUB ERP - Architectural Context & Guidelines

## Project Mission

To build an AI-native, Hub-and-Spoke ERP MVP for manufacturing.

- **Core Innovation**: Replacing linear workflows with parallel, agentic orchestration.
- **Key Features**: Parallel Quoting (Fan-Out/Fan-In), Dynamic Scheduling Entry (Schedule-First).

## Architecture Stack

| Layer | Technology |
|-------|------------|
| Infrastructure | Docker Compose on Ubuntu 24.04 (Digital Ocean) |
| Backend | Python 3.11 + FastAPI |
| Orchestration | LangGraph (Stateful Supervisor Pattern) |
| Database | PostgreSQL 16 (Async SQLAlchemy + pgvector) |
| Frontend | React 18 + Vite + TypeScript + Tailwind CSS |
| Messaging | Redis (for event bus and task queue) |

## Coding Standards (Strict Enforcement)

### Python
- Use Pydantic V2 for all data validation
- Use Async/Await for all I/O operations
- Follow PEP 8 style guidelines
- Type hints required for all functions

### Frontend
- Use Functional Components with Hooks
- Use Context API for global state
- Use Lucide-React for icons
- Component-driven architecture

### Database
- Use SQLAlchemy 2.0 declarative mapping
- Use Alembic for migrations
- Async database operations via asyncpg

### Agents
- All agents must be implemented as nodes in a LangGraph StateGraph
- Use the Supervisor pattern for orchestration
- Implement proper error handling and fallbacks

### Error Handling
- Global exception handlers in FastAPI
- Graceful degradation in UI
- Structured logging throughout

## Core Modules (The Spokes)

| Module | Responsibility |
|--------|----------------|
| **Hub (Supervisor)** | The LangGraph orchestrator that routes user intent |
| **Inventory Module** | Manages items, stock levels, and vendor details |
| **Scheduling Module** | Manages machines, production slots, and capacity |
| **Quoting Module** | Manages cost estimation and pricing logic |
| **Job Module** | The central entity tracking the lifecycle of an order |

## Critical Logic Patterns

### Parallel Execution
The Quoting workflow MUST trigger Inventory, Scheduling, and Costing checks **simultaneously** using LangGraph's parallel execution features (Fan-Out/Fan-In pattern).

### Dynamic Entry
A 'Job' record must be creatable WITHOUT a pre-existing Quote or Purchase Order. This enables the "Schedule-First" workflow where operations can proceed while finance catches up.

### Generative UI
The backend must return structured JSON that the frontend renders into rich widgets (Tables, Charts, Cards), not just text. The UI dynamically mounts components based on response type.

## API Design Principles

- RESTful endpoints for CRUD operations
- WebSocket for real-time updates
- Structured response format:
```json
{
  "type": "quote_options | job_status | chat_message | table | chart",
  "data": {},
  "message": "Human-readable message"
}
```

## File Structure

```
quantum_hub_erp/
├── backend/
│   ├── main.py              # FastAPI application entry
│   ├── database.py          # Database connection & session
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── hub.py               # LangGraph orchestrator
│   ├── config.py            # Configuration settings
│   ├── services/
│   │   ├── inventory.py     # Inventory spoke
│   │   ├── scheduling.py    # Scheduling spoke
│   │   ├── costing.py       # Costing spoke
│   │   └── job.py           # Job management
│   ├── agents/
│   │   ├── supervisor.py    # Supervisor agent
│   │   ├── inventory_agent.py
│   │   ├── scheduling_agent.py
│   │   └── costing_agent.py
│   └── alembic/             # Database migrations
├── frontend/
│   ├── src/
│   │   ├── components/      # React components
│   │   ├── contexts/        # React contexts
│   │   ├── hooks/           # Custom hooks
│   │   ├── services/        # API services
│   │   └── types/           # TypeScript types
│   └── public/
├── docker-compose.yml
├── nginx.conf
└── CLAUDE.md
```

## Environment Variables

```env
# Database
DATABASE_URL=postgresql+asyncpg://quantum:quantum@db:5432/quantum_hub

# Redis
REDIS_URL=redis://redis:6379

# AI Provider
ANTHROPIC_API_KEY=your_key_here

# Application
SECRET_KEY=your_secret_key
DEBUG=true
```
