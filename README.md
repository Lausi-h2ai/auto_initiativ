# Local-First Agentic Job Outreach

This repository defines the foundation for a personal, safety-first system for autonomous initiative job applications.

The core rule is simple: Codex agents may research, evaluate, draft, and write structured files, but they must never send email. The application backend is the source of truth for data, policies, dedupe, audit logging, and all email-sending decisions.

## Current Scope

This initial foundation contains:

- Product, architecture, onboarding, data model, safety gate, and workflow documentation.
- JSON schemas for agent-produced and backend-produced files.
- Agent boundary instructions for future Codex runs.
- Repository-level `AGENTS.md` instructions.

No email sending code is implemented. No OpenAI API dependency is introduced.

## Target Architecture

- Frontend: dashboard for runs, companies, applications, send queue, sent and blocked emails, audit logs, and settings.
- Backend: FastAPI, Postgres, SQLModel or SQLAlchemy, Pydantic validation, deterministic send gate, email adapter interfaces.
- Codex runtime: file-based worker runs with `input/`, `output/`, `logs/`, `task.md`, and `instructions.md`.

## Safety Model

Sending is impossible unless the deterministic backend gate validates a `send_intent.json`, checks dedupe and policy constraints, reserves the send transactionally, writes audit records, and only then calls the configured email adapter.

The first implementation phase should stay dry-run safe.

## Key Documents

- [Product spec](docs/PRODUCT_SPEC.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Agent boundaries](docs/AGENT_BOUNDARIES.md)
- [Safety gates](docs/SAFETY_GATES.md)
- [Onboarding spec](docs/ONBOARDING_SPEC.md)
- [Send intent spec](docs/SEND_INTENT_SPEC.md)
- [Codex workflow](docs/CODEX_WORKFLOW.md)
- [Data model](docs/DATA_MODEL.md)

## Schemas

Agent and backend JSON contracts live in `schemas/`. Any file imported from a Codex run must be validated against the matching schema before it can affect application state.

## Phase 1 Backend Setup

Install the backend with test dependencies using Python 3.11 or newer:

```powershell
uv sync --python 3.12 --extra test
```

Run tests:

```powershell
uv run --python 3.12 --extra test pytest
```

Run optional Postgres-backed migration/constraint tests by pointing `POSTGRES_TEST_DATABASE_URL` at a disposable Postgres test database:

```powershell
$env:POSTGRES_TEST_DATABASE_URL="postgresql+psycopg://user:password@localhost:5432/auto_initiativ_test"
uv run --python 3.12 --extra test pytest backend/tests/test_postgres_dedupe_constraints.py
```

Start the dry-run backend:

```powershell
uv run --python 3.12 uvicorn backend.app.main:app --reload
```

Apply database migrations to a fresh local database:

```powershell
uv run --python 3.12 alembic upgrade head
```

For an existing Phase 1 database created before Alembic was added, inspect it first and stamp only after confirming it matches the current schema:

```powershell
uv run --python 3.12 alembic current
uv run --python 3.12 alembic stamp head
```

Useful endpoints:

- `GET /health`
- `POST /runs/{run_id}/import`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/files`
- `GET /runs/{run_id}/validation-results`
- `GET /audit-logs`

Configuration uses environment variables. `DRY_RUN` defaults to `true`; `DATABASE_URL` defaults to a local SQLite database at `backend/dev.db`; `RUNS_ROOT` defaults to `runs/`; and `SCHEMAS_ROOT` defaults to `schemas/`.
