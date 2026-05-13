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

