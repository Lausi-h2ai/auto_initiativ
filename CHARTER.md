# Automode Charter

## 1. Product Mission

Build a personal, local-first, safety-first system for initiative job outreach.

The product helps one user research companies, evaluate fit, tailor CV material from approved claims, draft outreach, create structured send intents, and track outreach state. It must make autonomous work observable and keep irreversible decisions under deterministic backend control.

## 2. Current Phase

Current phase: Phase 3 and forward.

Phase 1 is complete and audited. Phase 2 is complete and audited in `docs/PHASE_2_FINAL_AUDIT.md`. The backend currently provides a dry-run FastAPI skeleton, schema-backed run-output import, operational persistence, normalized Phase 2 domain persistence, deterministic normalization, database-backed dedupe constraints, API inspection endpoints, and tests.

The next work is Phase 3: deterministic `evaluate_only` safety gate behavior. Phase 3 must not add email sending, Gmail access, OpenAI API usage, or an email adapter.

## 3. Non-Negotiable Safety Rules

- Agents produce files. Programs make decisions.
- Codex agents must never send email.
- Codex agents must never call Gmail.
- Codex agents must never add real email adapter sending without explicit later instruction.
- Codex agents must never bypass backend validation.
- Codex agents must never decide that safety gates pass.
- Codex agents must never modify production database state outside application logic.
- Codex agents must never invent user career facts.
- Codex agents must never introduce an OpenAI API dependency.
- Every agent output consumed by code must be structured, validated, and auditable.
- Dedupe must be enforced in the database, not only in prompts.

## 4. Architecture Summary

Frontend target:

- Dashboard for runs, companies, contacts, applications, send queue, sent and blocked emails, audit logs, and settings.

Backend target:

- FastAPI.
- Postgres as durable source of truth.
- SQLModel or SQLAlchemy.
- Pydantic and JSON Schema validation.
- Deterministic safety gate.
- Future email adapter behind an interface.
- No LLM dependency in safety logic.

Codex runtime target:

- Prepared run folders under `runs/<run_id>/`.
- Codex reads `input/`, `task.md`, and `instructions.md`.
- Codex writes structured files to `output/` and notes to `logs/`.
- Backend imports and validates outputs before they affect application state.

## 5. Agent/Program Boundary

Agents may:

- Research, summarize, draft, evaluate, and produce structured files.
- Mark uncertainty, source references, confidence, and review flags.
- Propose implementation plans and patches inside bounded ticks.

Agents must not:

- Send email.
- Call Gmail or an email adapter.
- Decide that a send intent is safe.
- Write unvalidated outreach state directly into the database.
- Invent career facts or unsupported personalization.

Programs must:

- Validate schemas.
- Enforce dedupe and policy.
- Persist source-of-truth state.
- Run deterministic safety gates.
- Write audit logs.
- Own all irreversible actions.

## 6. Current Implemented State After Phase 1

Implemented:

- FastAPI backend skeleton in `backend/app/`.
- `DRY_RUN=true` default.
- JSON Schema registry and validation for known agent output filenames.
- Pydantic helper models aligned to schemas.
- Run output import service for `runs/<run_id>/output/`.
- Minimal tables: `runs`, `imported_files`, `validation_results`, `audit_logs`.
- API endpoints for health, run import, runs, files, validation results, and audit logs.
- Tests covering valid imports, invalid JSON, schema failures, missing expected files, unsupported run types, audit logging, dry-run default, and no Gmail/OpenAI/email adapter boundary.
- Final Phase 1 audit: ready for Phase 2.

Implemented after Phase 2:

- Normalized domain models.
- Dedupe constraints.
- Alembic migration workflow.
- Fake deterministic Phase 2 seed fixtures.
- Import-to-domain normalization for schema-valid outputs.

Not implemented:

- Deterministic safety gate.
- Dashboard.
- Onboarding flow.
- Codex run orchestration.
- Email adapter interface.
- Gmail sending.

## 7. Default Stack Assumptions

- Python 3.12 for local development.
- `uv` for dependency and command execution.
- FastAPI for APIs.
- SQLModel or SQLAlchemy for persistence.
- Postgres for durable development and production-like local state from Phase 2 onward.
- SQLite may remain available only for lightweight tests or local smoke checks when compatible.
- Pydantic for API models.
- JSON Schema files in `schemas/` remain the import validation authority.
- Pytest for tests.

## 8. File and Directory Conventions

- `backend/app/`: backend application code.
- `backend/tests/`: backend tests and fixtures.
- `schemas/`: JSON Schema contracts.
- `docs/`: product, architecture, workflow, phase, and audit documents.
- `agents/`: agent-specific instructions for file-producing job outreach workers.
- `roles/`: Automode role prompts.
- `reviews/`: one review or audit report per tick.
- `archive/`: completed tick summaries and closed work notes.
- `adr/`: architecture decision records.
- `runs/`: generated Codex run folders and local runtime data; ignored by git.

## 9. Testing Expectations

Every implementation tick must run relevant tests before handoff.

Default full backend test command:

```powershell
uv run --python 3.12 --extra test pytest
```

Tests must cover:

- Validation and rejection paths.
- Audit logging for important actions and failures.
- Boundary assertions for no Gmail/OpenAI/email sending when relevant.
- Database constraints when persistence logic changes.
- API inspection behavior when endpoints change.

## 10. Review Expectations

Every non-trivial implementation tick must be reviewed against:

- This charter.
- `AGENTS.md`.
- Phase scope in `docs/IMPLEMENTATION_PLAN.md`.
- Agent/backend boundary.
- Safety rules.
- Tests and migration behavior.

Review findings must be concrete and file-referenced where possible.

## 11. Log and Commit Expectations

Each Automode tick must produce a verifiable artifact:

- A code/docs diff.
- A test result.
- A review report in `reviews/` or a tick summary in `archive/`.
- Blackboard updates in `BACKLOG.md` and/or `BUGS.md` when work opens or closes.

Recommended commit format:

```text
tick <number>: <short outcome>
```

Do not create commits unless the user/dispatcher asks for a commit in that tick. The tick should still end in a committable state whenever possible.

## 12. Human Role

The user is the project manager and dispatcher during Automode ticks.

The user:

- Chooses tick scope.
- Approves plans.
- Spawns roles.
- Reads summaries and review reports.
- Decides when to commit.
- Decides when locked future capabilities, such as real email sending, may be considered.

Agents execute bounded roles inside the charter. They do not silently change project direction.
