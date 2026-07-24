# Local-First Agentic Job Outreach

This repository defines the foundation for a personal, safety-first system for autonomous initiative job applications.

The core rule is simple: Codex agents may research, evaluate, draft, and write structured files, but they must never send email. The application backend is the source of truth for data, policies, dedupe, audit logging, and all email-sending decisions.

## Current Scope

The current implementation contains:

- Product, architecture, onboarding, data model, safety gate, and workflow documentation.
- JSON schemas for agent-produced and backend-produced files.
- Restricted Pi RPC agent workloads for onboarding, research, verification, and application drafting.
- Durable campaigns, graph-correlated workflow tasks, deterministic imports and gates, transactional send reservations, and audit records.
- Repository-level `AGENTS.md` instructions.

Email sending is disabled by default and remains reachable only through the privileged backend gate and reservation path. No direct OpenAI API dependency is introduced.

## Target Architecture

- Frontend: dashboard for runs, companies, applications, send queue, sent and blocked emails, audit logs, and settings.
- Backend: FastAPI, Postgres, SQLModel or SQLAlchemy, Pydantic validation, deterministic send gate, email adapter interfaces.
- Codex runtime: file-based worker runs with `input/`, `output/`, `logs/`, `task.md`, and `instructions.md`.

## Workflow Graph Architecture

Auto Initiativ uses graph engineering as an application architecture, not as a second agent runtime. Workflows are modeled as versioned graphs of deterministic backend operations, narrowly scoped agent runs, fan-out/fan-in barriers, bounded remediation cycles, human interrupts, and privileged side-effect boundaries.

The framework path is deliberately application-owned:

- Trusted graph definitions and topology validation live in `backend/app/workflow/graph.py`.
- Postgres remains the sole durable source of truth. Framework checkpoints or agent memory must not become competing state stores.
- `AgentTask` records graph definition, version, run, node, parent, and stable execution-key correlation.
- Pi RPC remains the restricted runtime for file-producing agent nodes.
- Registered backend predicates select edges. Agents may provide schema-valid evidence, but they may not select transitions, allocate budgets, approve work, or create graph topology.
- Every cycle must have an application-enforced attempt, time, or budget bound.
- External work must be idempotent and reconciled. An uncertain external or provider outcome must block rather than relaunch automatically.

The current definitions are:

- `coordinated_research` v1: confirmed-plan interrupt, target research fan-out, bounded shared-budget cycles, deterministic fan-in, scope assessment, ranking, and retention.
- `application_preparation` v1: contact decision and bounded remediation, candidate drafting, deterministic claim/source/artifact validation, and review/ready/blocked outcomes.
- `privileged_sending` v1: validated intent, authorized frozen approval, deterministic evaluate-only gate, transactional reservation, provider attempt, and audited terminal outcomes.

Coordinated research currently runs in shadow/correlation mode: the existing workflow engine remains authoritative while graph identities and observed transitions are audited. Application preparation and privileged sending are static validated boundaries and have not been cut over to a generic graph dispatcher. Promotion from shadow mode requires reviewed mismatch evidence, graph-level regression tests, atomic claiming and idempotency guarantees, and an explicit implementation tick. The project does not currently adopt LangGraph, the OpenAI Agents SDK, or another workflow checkpoint runtime.

The detailed decision, invariants, migration stages, and rejected alternatives are recorded in [ADR-0003](adr/0003-application-owned-workflow-graph.md).

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
- [Application-owned workflow graph ADR](adr/0003-application-owned-workflow-graph.md)

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

## Local Development Accounts

With `AUTH_REQUIRED=false`, open **Settings → Create or switch local account** or visit `http://127.0.0.1:8000/register`. The registration screen creates an isolated workspace and switches the browser to it immediately; no Google setup or server restart is required.

`DEV_AUTH_BYPASS_EMAIL` remains the fallback account when the browser has no selected local session. The app creates its workspace automatically the first time it sees a new fallback email:

```text
AUTH_REQUIRED=false
DEV_AUTH_BYPASS_EMAIL=fresh-test-01@local.invalid
```

Changing the email creates or switches to another workspace without deleting the previous one. For a completely blank database and run directory as well, point `DATABASE_URL` and `RUNS_ROOT` at new paths before restarting:

```text
DATABASE_URL=sqlite:///F:/auto_initiativ/backend/dev-fresh-01.db
RUNS_ROOT=F:/auto_initiativ/runs-fresh-01
```

When `AUTH_REQUIRED=true`, accounts remain invite-only. An administrator adds an email under **Administration**, then that user signs in with Google and receives a fresh private workspace.

## Local Gmail Credentials

In local development mode (`AUTH_REQUIRED=false`), the backend reuses the existing machine-local Gmail files when both paths exist:

```text
GMAIL_OAUTH_CLIENT_SECRETS_PATH=...
GMAIL_OAUTH_TOKEN_PATH=...
GMAIL_USER_ID=me
```

This preserves the original single-machine workflow without requiring the newer Google web-login configuration. Authenticated or multi-user deployments never share these files; they require a per-user Gmail connection. Keep the local server bound to `127.0.0.1` when authentication is disabled.
