# Automode Backlog

Status values: `open`, `in_progress`, `blocked`, `review`, `done`, `locked`.

Priority values: `P0` critical, `P1` next, `P2` soon, `P3` later.

## Next Recommended Tick

### AM-002-005: Add Phase 2 Seed Fixtures

- Status: `open`
- Priority: `P2`
- Suggested roles: `IMPLEMENTER`, `TESTER`
- Goal: create local development fixtures for profiles, policies, companies, contacts, and send intents.
- Inputs: `CHARTER.md`, `docs/PHASE_2_TASK_BREAKDOWN.md`, current Phase 2 models, normalization helpers, dedupe constraints, schemas, tests.
- Outputs: fake local seed fixtures and deterministic fixture tests.
- Acceptance:
  - Fixtures are fake and safe.
  - No real personal or email credentials.
  - Tests can use fixtures deterministically.
  - Existing tests still pass.
  - No gate execution, email adapter, Gmail sending, or OpenAI API usage.

## Phase 2: Database Model And Dedupe

### AM-002-001: Phase 2 Planning Tick

- Status: `done`
- Priority: `P1`
- Suggested roles: `ORCHESTRATOR`, `RESEARCHER`, `REVIEWER`
- Goal: create a bounded Phase 2 implementation plan for normalized database models, migrations, and dedupe constraints without coding.
- Inputs: `CHARTER.md`, `docs/PHASE_1_FINAL_AUDIT.md`, `docs/DATA_MODEL.md`, `docs/IMPLEMENTATION_PLAN.md`, schemas, backend models/tests.
- Outputs: `docs/PHASE_2_TASK_BREAKDOWN.md` and any needed ADR proposal.
- Acceptance:
  - Identifies exact Phase 2 entities and constraints.
  - Defines migration approach.
  - Separates Phase 2 persistence/dedupe from Phase 3 gate logic.
  - Lists tests for duplicate recipient/company constraints.
  - Keeps Gmail sending, OpenAI usage, and gate execution out of scope.

### AM-002-002: Select Migration Strategy

- Status: `done`
- Priority: `P1`
- Goal: decide whether to add Alembic now and document migration workflow.
- Acceptance:
  - ADR created if a new migration tool or workflow is adopted.
  - Tests still run locally.
  - No production-like destructive migrations.

### AM-002-003: Define Normalized Phase 2 Tables

- Status: `done`
- Priority: `P1`
- Goal: add source-of-truth models for profile snapshots, master CV snapshots, policy snapshots, companies, contacts, evaluations, drafts, send intents, and supporting audit links.
- Acceptance:
  - Models remain dry-run safe.
  - No gate execution.
  - No email adapter.
  - Existing Phase 1 import tables remain intact.
  - Completed by `archive/tick-002-003.md`.

### AM-002-004: Add Database Dedupe Constraints

- Status: `done`
- Priority: `P1`
- Goal: enforce duplicate recipient/company prevention in the database according to stored policy fields.
- Acceptance:
  - Recipient email normalization is deterministic.
  - Company domain/key normalization is deterministic.
  - Tests prove duplicates fail under policy.
  - Prompt-only dedupe is not relied on.
  - Completed by `archive/tick-002-004.md`.

### AM-002-005: Add Phase 2 Seed Fixtures

- Status: `open`
- Priority: `P2`
- Goal: create local development fixtures for profiles, policies, companies, contacts, and send intents.
- Acceptance:
  - Fixtures are fake and safe.
  - No real personal or email credentials.
  - Tests can use fixtures deterministically.

### AM-002-006: Import Valid Outputs Into Domain Tables

- Status: `open`
- Priority: `P2`
- Goal: extend import processing so schema-valid outputs can be normalized into Phase 2 tables.
- Acceptance:
  - Invalid outputs remain rejected.
  - Raw import records remain auditable.
  - Domain normalization has tests.

## Phase 3: Deterministic Gate

### AM-003-001: Reconcile Gate Status Schema And Docs

- Status: `open`
- Priority: `P1`
- Goal: align `schemas/gate_result.schema.json`, Pydantic models, fixtures, and `docs/SAFETY_GATES.md`.
- Acceptance:
  - `sent` and `send_failed` are not gate statuses.
  - Gate modes are `evaluate_only` and future `reserve_for_send`.
  - Tests cover allowed and rejected statuses.

### AM-003-002: Implement Evaluate-Only Gate

- Status: `open`
- Priority: `P1`
- Goal: implement deterministic `evaluate_only` gate checks without reservation or sending.
- Acceptance:
  - Checks schema validity, dedupe state, policy, blocked domains, sources, attachments, limits, forbidden claims, claim IDs, contact safety, confidence, and review flags.
  - Writes pre/post audit logs.
  - Blocks by default on missing or ambiguous data.
  - No email adapter.

### AM-003-003: Gate Test Matrix

- Status: `open`
- Priority: `P1`
- Goal: add tests for every required blocking reason.
- Acceptance:
  - Each gate reason has a focused test.
  - Gate is deterministic with the same DB snapshot.

## Phase 4: Dashboard MVP

### AM-004-001: Dashboard Scope Plan

- Status: `open`
- Priority: `P2`
- Goal: plan the dashboard views and API needs.
- Acceptance:
  - Covers runs, companies, contacts, evaluations, drafts, send queue, blocked intents, and audit logs.
  - No marketing landing page.

### AM-004-002: Build Dashboard MVP

- Status: `open`
- Priority: `P2`
- Goal: implement a local dashboard for inspectability.
- Acceptance:
  - Shows backend state, not agent assumptions.
  - Supports filtering by status/reason/confidence/review flags.

## Phase 5: Onboarding Flow

### AM-005-001: Onboarding Data Contract Plan

- Status: `open`
- Priority: `P2`
- Goal: plan onboarding run inputs, outputs, review states, and snapshot promotion.
- Acceptance:
  - Distinguishes verified documents, user claims, inferred information, and needs-review items.
  - Exclusions are learned and stored in `policy.json`.

### AM-005-002: Onboarding Review Workflow

- Status: `open`
- Priority: `P2`
- Goal: implement review/promotion for `user_profile.json`, `master_cv_profile.json`, and `policy.json`.
- Acceptance:
  - Future CV tailoring uses approved master CV claims only.
  - Unapproved claims cannot be used automatically.

## Phase 6: Codex Run Orchestration

### AM-006-001: Run Folder Generator

- Status: `open`
- Priority: `P2`
- Goal: create backend-supported run folders with `input/`, `output/`, `logs/`, `task.md`, and `instructions.md`.
- Acceptance:
  - Agents receive scoped context only.
  - Secrets and send capabilities are never included.

### AM-006-002: Run Import Integration

- Status: `open`
- Priority: `P2`
- Goal: connect generated runs to import and dashboard visibility.
- Acceptance:
  - Every run is reproducible and inspectable.
  - Outputs remain schema validated.

## Phase 7: Email Adapter Interface

### AM-007-001: Fake Adapter Interface Only

- Status: `open`
- Priority: `P3`
- Goal: define an email adapter interface and fake dry-run adapter without real sending.
- Acceptance:
  - Adapter cannot be reached without passed gate and reservation.
  - Real Gmail sending remains unimplemented.

### AM-007-002: Reservation Preconditions

- Status: `open`
- Priority: `P3`
- Goal: test that future adapter handoff requires `reserve_for_send` and transactional reservation.
- Acceptance:
  - No real send path exists.
  - Tests prove direct adapter invocation is impossible through public APIs.

## Locked Future Placeholders

### AM-FUTURE-001: Real Gmail Adapter

- Status: `locked`
- Priority: `P3`
- Unlock condition: explicit user instruction after Phase 7 fake adapter, Phase 3 gate, and reservation tests are complete.
- Must remain behind deterministic backend gate.

### AM-FUTURE-002: Autonomous Sending

- Status: `locked`
- Priority: `P3`
- Unlock condition: explicit user instruction after dry-run gate, dedupe, reservations, audit logging, dashboard review, and adapter interface are proven.
- Must support immediate disabling and conservative send limits.
