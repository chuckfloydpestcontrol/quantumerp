# Quantum HUB ERP

An AI-native, Hub-and-Spoke Enterprise Resource Planning system for manufacturing.

## Overview

Quantum HUB ERP replaces traditional linear manufacturing workflows with parallel, AI-driven orchestration. The system uses a LangGraph-powered "Hub" to coordinate independent "Spoke" services, enabling features like parallel quoting and schedule-first job creation.

### Key Features

- **Parallel Quoting (Fan-Out/Fan-In)**: Get three quote options (Fastest, Cheapest, Balanced) calculated simultaneously
- **Dynamic Entry (Schedule-First)**: Schedule production capacity before financial documents are ready
- **Prompt-Driven Interface**: Natural language interaction with Generative UI components
- **Real-time Orchestration**: AI-powered workflow coordination using Claude

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Quantum HUB (LangGraph)                  │
│                    ┌─────────────────────┐                  │
│                    │  Supervisor Agent   │                  │
│                    └─────────┬───────────┘                  │
│         ┌──────────────┬─────┴─────┬──────────────┐        │
│         ▼              ▼           ▼              ▼        │
│   ┌──────────┐  ┌──────────┐ ┌──────────┐  ┌──────────┐   │
│   │Inventory │  │Scheduling│ │ Costing  │  │   Job    │   │
│   │  Spoke   │  │  Spoke   │ │  Spoke   │  │  Spoke   │   │
│   └──────────┘  └──────────┘ └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘
```

## Tech Stack

| Layer | Technology |
|-------|------------|
| **Frontend** | React 18, TypeScript, Tailwind CSS, Vite |
| **Backend** | Python 3.11, FastAPI, SQLAlchemy 2.0 |
| **AI Orchestration** | LangGraph, Claude (Anthropic) |
| **Database** | PostgreSQL 16 with pgvector |
| **Cache** | Redis |
| **Infrastructure** | Docker Compose, Nginx |

## Quick Start

### Prerequisites

- Docker and Docker Compose
- Anthropic API key

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/chuckfloydpestcontrol/quantumerp.git
   cd quantumerp
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env and add your ANTHROPIC_API_KEY
   ```

3. **Start the services**
   ```bash
   docker compose up -d
   ```

4. **Seed demo data** (optional)
   ```bash
   curl -X POST http://localhost:8000/api/seed
   ```

5. **Access the application**
   - Frontend: http://localhost:3000
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

## Usage Examples

### Get a Quote
```
"Quote 25 custom brackets for Acme Corp, aluminum, need by Friday"
```

### Schedule Production (Dynamic Entry)
```
"Emergency! Schedule 50 units of Part-Y for immediate production. PO coming Monday."
```

### Check Job Status
```
"What's the status of job 20241231-0001?"
```

### View Production Schedule
```
"Show me the production schedule"
```

## API Endpoints

### Chat (Primary Interface)
- `POST /api/chat` - Send message to Quantum HUB AI

### Jobs
- `GET /api/jobs` - List all jobs
- `POST /api/jobs` - Create a job
- `POST /api/jobs/dynamic` - Create job with Dynamic Entry (schedule-first)
- `GET /api/jobs/{id}` - Get job details
- `POST /api/jobs/{id}/attach-po` - Attach PO number

### Inventory
- `GET /api/items` - List inventory items
- `GET /api/items/check-stock/{id}` - Check stock availability

### Scheduling
- `GET /api/schedule` - Get production schedule
- `GET /api/schedule/find-slot` - Find available machine slot

### Quoting
- `POST /api/quotes/parallel` - Generate parallel quote options

## Project Structure

```
├── backend/
│   ├── main.py              # FastAPI application
│   ├── hub.py               # LangGraph orchestrator
│   ├── models.py            # SQLAlchemy models
│   ├── schemas.py           # Pydantic schemas
│   ├── services/            # Spoke services
│   │   ├── inventory.py
│   │   ├── scheduling.py
│   │   ├── costing.py
│   │   └── job.py
│   └── alembic/             # Database migrations
├── frontend/
│   ├── src/
│   │   ├── App.tsx          # Main application
│   │   ├── components/      # React components
│   │   ├── contexts/        # React contexts
│   │   └── services/        # API services
│   └── public/
├── docker-compose.yml
├── nginx.conf
└── README.md
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_API_KEY` | Anthropic API key for Claude | Yes |
| `DATABASE_URL` | PostgreSQL connection string | Yes |
| `REDIS_URL` | Redis connection string | Yes |
| `SECRET_KEY` | Application secret key | Yes |
| `DEBUG` | Enable debug mode | No |

## Development

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --reload
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

### Database Migrations
```bash
cd backend
alembic upgrade head
```

## License

Proprietary - All rights reserved.
