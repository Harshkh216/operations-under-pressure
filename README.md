# Operations Under Pressure

An enterprise operations dashboard for managing critical work items under deadline pressure. Built as the Newtonite Software Engineering Challenge project.

## Overview

Operations teams manage a queue of work items — incidents, patches, operational tasks — that flow through a state machine from creation to completion. The app enforces team isolation, role-based access control, optimistic concurrency, and reliable event delivery via a transactional outbox.

**Key features:**
- JWT-based login with per-team roles (manager / contributor)
- Dashboard with summary cards (Assigned to Me, Unassigned Urgent, Awaiting Approval)
- Server-side paginated, searchable, filterable work-item table
- Work-item detail page with claim, status transitions, comments, and activity timeline
- Create and edit task forms (managers only)
- Optimistic concurrency (version-based stale-update rejection → HTTP 409)
- Idempotency via `Idempotency-Key` header on POST/PUT
- Transactional activity history (written in the same DB transaction as the mutation)
- Transactional outbox with background worker for at-least-once event delivery
- Proper handling of 401 (session expired), 403 (forbidden), and 409 (conflict) responses

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   Next.js 13    │     │  FastAPI (uvicorn)│     │  PostgreSQL     │
│   Frontend      │────▶│  Backend          │────▶│  (Supabase or   │
│                 │     │                  │     │   Docker)       │
│  React + TS     │     │  SQLAlchemy ORM  │     │                 │
│  Tailwind +     │     │  Alembic migr.   │     │  teams          │
│  shadcn/ui      │     │  Pytest suite    │     │  users          │
│                 │     │                  │     │  work_items     │
│  /login         │     │  /api/login      │     │  comments       │
│  /dashboard     │     │  /api/work-items │     │  activity_events│
│  /dashboard/*   │     │  /api/outbox     │     │  outbox_events  │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                              │
                              ▼
                        ┌──────────┐
                        │ Outbox   │  Background asyncio task
                        │ Worker   │  drains pending events
                        └──────────┘
```

**Tech stack:**
- Frontend: Next.js 13, React 18, TypeScript, Tailwind CSS, shadcn/ui, Lucide icons
- Backend: Python FastAPI, SQLAlchemy 2.0, Alembic, Pydantic 2
- Database: PostgreSQL (production via Supabase or Docker; SQLite for local tests)
- Auth: JWT (python-jose) + bcrypt password hashing

## Prerequisites

- Node.js 18+ and npm
- Python 3.11+ and pip
- Docker and Docker Compose (for containerized setup)
- PostgreSQL 14+ (or use the Dockerized instance)

## Setup & Run

### Option A: Docker Compose (recommended)

```bash
# Copy env and adjust if needed
cp .env.example .env

# Build and start all services (Postgres + backend + frontend)
docker-compose up --build

# The backend auto-runs migrations and seeds on startup.
# Frontend: http://localhost:3000
# Backend API: http://localhost:8001
# API docs (Swagger): http://localhost:8001/docs
```

### Option B: Local development

**1. Start the backend:**

```bash
cd backend
pip install -r requirements.txt

# Set environment variables (or create a .env file)
export DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/operations"
export JWT_SECRET_KEY="your-secret-key"
export OUTBOX_ENABLED=true

# Run migrations
alembic upgrade head

# Seed demo data
python -m app.seed

# Start the server
uvicorn app.main:app --port 8001 --reload
```

**2. Start the frontend:**

```bash
# From the project root
npm install

# Set the API URL
export NEXT_PUBLIC_API_URL=http://localhost:8001

npm run dev
# Open http://localhost:3000
```

### Hosted deployment

The frontend cannot reach `localhost:8001` when it is hosted. Deploy the `backend/` Docker image to a service that provides a public HTTPS URL and configure these backend variables there:

- `DATABASE_URL`: a reachable PostgreSQL connection string
- `JWT_SECRET_KEY`: a long random production secret
- `BACKEND_CORS_ORIGINS`: the exact HTTPS origin serving the frontend
- `OUTBOX_ENABLED`: `true` or `false` as appropriate

Run `alembic upgrade head && python -m app.seed && uvicorn app.main:app --host 0.0.0.0 --port 8001` in the backend service. Set the frontend build variable `NEXT_PUBLIC_API_URL` to that backend's HTTPS URL, then verify its `/health` endpoint reports both `status: ok` and `database: ok`.

**3. For local testing with SQLite (no Postgres needed):**

```bash
cd backend
export DATABASE_URL="sqlite:///./test.db"
alembic upgrade head
python -m app.seed
uvicorn app.main:app --port 8001
```

## API Documentation

Interactive API docs are available at **http://localhost:8001/docs** (Swagger UI) when the backend is running.

### Key endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/login` | Authenticate, returns JWT + user info |
| GET | `/api/me` | Current user with team memberships |
| GET | `/api/teams` | List current user's teams |
| GET | `/api/dashboard/summary` | Dashboard summary counts |
| GET | `/api/work-items` | List work items (paginated, filterable) |
| POST | `/api/work-items` | Create a work item (managers only) |
| GET | `/api/work-items/{id}` | Get a single work item |
| PUT | `/api/work-items/{id}` | Update a work item (version required) |
| POST | `/api/work-items/{id}/transition` | Transition status (claim, approve, etc.) |
| POST | `/api/work-items/{id}/comments` | Add a comment |
| GET | `/api/work-items/{id}/comments` | List comments |
| GET | `/api/work-items/{id}/activity` | Activity timeline |
| GET | `/api/outbox` | List outbox events |
| POST | `/api/outbox/drain` | Manually drain pending outbox events |

## Demo Credentials

All accounts use the password **`password123`**.

| Email | Role | Team |
|-------|------|------|
| manager@alpha.ops | Manager | Team Alpha |
| alice@alpha.ops | Contributor | Team Alpha |
| manager@beta.ops | Manager | Team Beta |
| bob@beta.ops | Contributor | Team Beta |

## Migrations & Seed

```bash
cd backend

# Apply migrations
alembic upgrade head

# Seed demo data (idempotent — safe to run multiple times)
python -m app.seed

# Rollback (if needed)
alembic downgrade -1
```

## Tests

### Backend (Python)

```bash
cd backend

# Run the full test suite (uses in-memory SQLite — no Postgres required)
DATABASE_URL="sqlite:///" OUTBOX_ENABLED=false python -m pytest tests/ -v

# Run a specific test file
python -m pytest tests/test_workflow.py -v
```

The test suite covers: authentication, role-based authorization, team isolation, atomic claiming, optimistic concurrency (stale version → 409), idempotency, workflow transitions, activity history, outbox processing, and pagination/filtering.

**43 tests, all passing.**

### Frontend (TypeScript)

```bash
# Type checking
npm run typecheck

# Production build
npm run build
```

**Build succeeds — all 10 routes compile.**

## Known Limitations

1. **Outbox delivery is a no-op sink in demo mode.** Set `OUTBOX_SINK_URL` to an HTTP endpoint to deliver events to a real downstream system.
2. **Contributors can only assign to themselves** when editing; full reassignment is manager-only.
3. **No real-time updates.** The frontend polls on page load; WebSocket/SSE push is not implemented.
4. **JWT tokens are stateless** — there is no server-side revocation list. Token expiry (8h) is the only invalidation mechanism.
5. **The assignee dropdown in the edit form** only lists the current user; in production this would show all team members.
6. **Tests run against SQLite** for speed and isolation. The production schema is verified against Supabase PostgreSQL via the MCP migration tool.

## Project Structure

```
.
├── app/                          # Next.js app router pages
│   ├── login/                    # Login page
│   ├── dashboard/                # Dashboard with sidebar layout
│   │   ├── page.tsx              # Main dashboard with summary + table
│   │   ├── assigned/             # Assigned to Me view
│   │   ├── urgent/               # Unassigned Urgent view
│   │   ├── approvals/            # Awaiting My Approval view
│   │   └── work-items/
│   │       ├── [id]/             # Task detail page
│   │       ├── new/              # Create task form
│   │       └── edit/[id]/        # Edit task form
│   ├── layout.tsx                # Root layout (AuthProvider + Toaster)
│   └── page.tsx                  # Root redirect
├── components/                   # Shared UI components
│   ├── ui/                       # shadcn/ui primitives
│   ├── work-item-table.tsx       # Paginated work-item table
│   └── summary-cards.tsx         # Dashboard summary cards
├── lib/                          # Frontend utilities
│   ├── api.ts                    # API client (fetch wrapper)
│   ├── auth-context.tsx          # React auth context
│   ├── types.ts                  # TypeScript types
│   └── badges.ts                 # Priority/status badge helpers
├── backend/                      # Python FastAPI backend
│   ├── app/
│   │   ├── main.py               # FastAPI app factory
│   │   ├── core/                 # Config, security, auth deps
│   │   ├── db/                   # SQLAlchemy engine + session
│   │   ├── models/               # ORM models
│   │   ├── schemas/              # Pydantic schemas
│   │   ├── services/             # Workflow state machine + outbox
│   │   ├── api/                  # Route handlers
│   │   └── seed.py               # Demo data seeder
│   ├── alembic/                  # Migration scripts
│   ├── tests/                    # Pytest suite (9 files, 43 tests)
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic.ini
├── docker-compose.yml
├── frontend.Dockerfile
├── .env.example
└── ENGINEERING_DECISIONS.md
```
