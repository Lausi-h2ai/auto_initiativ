# Automode Backlog

Status values: `open`, `in_progress`, `blocked`, `review`, `done`, `locked`.

Priority values: `P0` critical, `P1` next, `P2` soon, `P3` later.

## Next Recommended Tick

### AM-008-002: First-Class Onboarding Session Records

- Status: `open`
- Priority: `P1`
- Suggested roles: `ORCHESTRATOR`, `IMPLEMENTER`, `TESTER`, `REVIEWER`
- Goal: move onboarding sessions from file-backed state to first-class database records tied to the active profile and tmux attachment metadata.
- Inputs: `docs/PRODUCT_REALIGNMENT_PLAN.md`, `docs/CODEX_TMUX_BRIDGE_PLAN.md`, profile shell, onboarding chat adapter.
- Outputs: onboarding session model/API/UI wiring and migration/tests.
- Acceptance:
  - Onboarding session records store run ID, active profile shell, tmux target metadata, status, start/end timestamps, and latest transport state.
  - Transcript remains persisted and inspectable.
  - Existing file-backed state can be read or migrated without data loss.
  - No automatic promotion, Gmail, real email adapter sending, OpenAI API dependency, autonomous sending, or backend gate bypass.

## Product Realignment And Tmux Workflow

### AM-006-REFINE: Product Workflow And Codex Tmux Bridge Alignment

- Status: `done`
- Priority: `P1`
- Goal: realign the product toward a local personal AI recruiter workflow and refine the existing tmux bridge for live onboarding and campaign research.
- Outputs:
  - `docs/CODEX_TMUX_BRIDGE_PLAN.md`
  - `docs/PRODUCT_REALIGNMENT_PLAN.md`
  - `reviews/AM-006-REFINE_TMUX_BRIDGE_ALIGNMENT.md`
- Acceptance:
  - Current tmux bridge behavior is documented.
  - Backend bridge functions cover fresh session/window startup, app-session attachment, prompting, capture/new-output reads, liveness, session listing, graceful close, and force-kill.
  - Backend-owned state remains the source of truth.
  - Main product UX is steered toward profiles, onboarding, campaigns, campaign research, company import/review, and later gated outreach.
  - Internal runs, gate results, audit logs, validation results, and send queue are treated as Developer Logs/secondary navigation.
  - No Gmail, real email adapter sending, OpenAI API dependency, autonomous sending, backend gate bypass, or safety infrastructure removal.

### AM-006-004: Profile Shell And Onboarding Chat UX

- Status: `done`
- Priority: `P1`
- Goal: build the first product-facing setup journey: a Profile page that detects missing approved profile state and starts a tmux-backed Codex onboarding chat.
- Outputs:
  - Profile summary API.
  - File-backed onboarding session state API.
  - Product-facing Profile dashboard page with Start Onboarding, Read Output, Reset, and Close controls.
  - `reviews/AM-006-004_PROFILE_ONBOARDING_CHAT_UX.md`
- Acceptance:
  - User can open the app, see missing approved profile state, start onboarding, and chat with Codex in tmux.
  - Transcript and session state are persisted by backend-owned files under the run logs folder.
  - Codex process state and backend session state remain separated.
  - Failures are visible in the UI and recorded as failed session state.
  - Existing Developer Logs remain secondary.
  - No Gmail, real email adapter sending, OpenAI API dependency, autonomous sending, backend gate bypass, campaign building, or full profile extraction.

### AM-006-005: Onboarding Recruiter Prompt And Profile Artifact Extraction

- Status: `done`
- Priority: `P1`
- Goal: make the tmux-backed onboarding Codex session behave as a private recruiter and produce schema-validated candidate profile artifacts.
- Outputs:
  - Recruiter prompt builder for onboarding tmux sessions.
  - Backend artifact status and validation/import endpoints.
  - Dashboard artifact status panel and validation control.
  - `reviews/AM-006-005_ONBOARDING_RECRUITER_ARTIFACTS.md`
- Acceptance:
  - Starting onboarding sends recruiter instructions once per run without exposing the prompt as a user chat message.
  - Codex is instructed to write `user_profile.json`, `master_cv_profile.json`, `policy.json`, and `onboarding_review.json` under `runs/<run_id>/output/`.
  - Artifact files are schema validated and imported as candidate/unapproved snapshots where applicable.
  - The UI shows missing, invalid, candidate, and ready-for-review artifact state.
  - Promotion remains explicit and backend-owned.
  - No Gmail, real email adapter sending, OpenAI API dependency, autonomous sending, campaign implementation, automatic promotion, or backend gate bypass.

### AM-008-001: Profile Shell And Active Profile Selection

- Status: `done`
- Priority: `P1`
- Goal: create the first user-facing profile shell so the app starts from a selected local profile instead of an operations table.
- Acceptance:
  - User can see approved/candidate profile state from the Profile page.
  - Missing approved profile state routes to the onboarding chat.
  - Internal runs, validation, gate results, and audit logs remain available under Developer Logs, not the primary UX.
  - No Gmail, real email adapter sending, OpenAI API dependency, autonomous sending, or backend gate bypass.
  - Completed by `reviews/AM-006-004_PROFILE_ONBOARDING_CHAT_UX.md`.

### AM-008-002: First-Class Onboarding Session Records

- Status: `open`
- Priority: `P1`
- Goal: move onboarding sessions from transcript-file-only state to backend source-of-truth records tied to the active profile and tmux attachment metadata.
- Acceptance:
  - Onboarding session record stores run ID, active profile shell, tmux target metadata, status, start/end timestamps, and latest transport state.
  - Transcript remains persisted and inspectable.
  - Finish action imports candidate profile/master CV/policy outputs through existing schema validation.
  - No automatic promotion.

### AM-008-003: Campaign Creation

- Status: `open`
- Priority: `P1`
- Goal: let the user create regional job-search campaigns from an approved profile/policy context.
- Acceptance:
  - Campaign record stores region, target roles, constraints, source profile/policy snapshots, status, and audit metadata.
  - Campaign creation does not launch outreach or generate send intents.
  - Campaigns are visible as a primary product view.

### AM-008-004: Campaign Research Tmux Run

- Status: `open`
- Priority: `P1`
- Goal: launch a long-running Codex research agent in a campaign-specific tmux window and import found companies.
- Acceptance:
  - Backend starts or attaches a campaign tmux window using the bridge.
  - Research agent receives scoped context only.
  - Transport logs are captured for Developer Logs.
  - `company_candidate.json` outputs are schema validated and imported.
  - No send intent generation in this tick.

### AM-008-005: Company Import List And Detail Review

- Status: `open`
- Priority: `P1`
- Goal: make imported companies the main review surface after campaign research.
- Acceptance:
  - Company list supports campaign filters, fit/review/policy flags, and source visibility.
  - Company detail shows evidence, policy conflicts, contacts/fit when present, raw imported data, and audit links.
  - User review state is backend-owned.

### AM-008-006: Later Gated Outreach UX

- Status: `open`
- Priority: `P2`
- Goal: design the later user-facing outreach review flow without enabling real sending.
- Acceptance:
  - Drafts and send intents are presented only after company/contact review.
  - Deterministic evaluate-only and future reserve-for-send gates remain mandatory.
  - Send queue stays secondary until explicit future unlock work.
  - No Gmail or real sending.

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

- Status: `done`
- Priority: `P2`
- Goal: create local development fixtures for profiles, policies, companies, contacts, and send intents.
- Acceptance:
  - Fixtures are fake and safe.
  - No real personal or email credentials.
  - Tests can use fixtures deterministically.
  - Completed by `archive/tick-002-005.md`.

### AM-002-006: Import Valid Outputs Into Domain Tables

- Status: `done`
- Priority: `P2`
- Goal: extend import processing so schema-valid outputs can be normalized into Phase 2 tables.
- Acceptance:
  - Invalid outputs remain rejected.
  - Raw import records remain auditable.
  - Domain normalization has tests.
  - Completed by `archive/tick-002-006.md`.

### AM-002-007: Phase 2 Audit

- Status: `done`
- Priority: `P1`
- Goal: audit Phase 2 for readiness before Phase 3 deterministic gate work.
- Acceptance:
  - Confirms normalized persistence and dedupe constraints are complete.
  - Confirms seed fixtures and import-to-domain normalization are complete.
  - Confirms no gate execution, email adapter, Gmail sending, or OpenAI API usage.
  - Existing tests still pass.
  - Lists remaining risks before Phase 3.
  - Completed by `docs/PHASE_2_FINAL_AUDIT.md` and `archive/tick-002-007.md`.

## Phase 3: Deterministic Gate

### AM-003-001: Reconcile Gate Status Schema And Docs

- Status: `done`
- Priority: `P1`
- Goal: align `schemas/gate_result.schema.json`, Pydantic models, fixtures, and `docs/SAFETY_GATES.md`.
- Acceptance:
  - `sent` and `send_failed` are not gate statuses.
  - Gate modes are `evaluate_only` and future `reserve_for_send`.
  - Tests cover allowed and rejected statuses.
  - Completed by `archive/tick-003-001.md`.

### AM-003-002: Implement Evaluate-Only Gate

- Status: `done`
- Priority: `P1`
- Goal: implement deterministic `evaluate_only` gate checks without reservation or sending.
- Acceptance:
  - Checks schema validity, dedupe state, policy, blocked domains, sources, attachments, limits, forbidden claims, claim IDs, contact safety, confidence, and review flags.
  - Writes pre/post audit logs.
  - Blocks by default on missing or ambiguous data.
  - No email adapter.
  - Completed by `archive/tick-003-002.md`.

### AM-003-003: Gate Test Matrix

- Status: `done`
- Priority: `P1`
- Goal: add tests for every required blocking reason.
- Acceptance:
  - Each gate reason has a focused test.
  - Gate is deterministic with the same DB snapshot.
  - Completed by `reviews/tick-003-003-gate-test-matrix.md` and `archive/tick-003-003.md`.

## Phase 4: Dashboard MVP

### AM-004-001: Dashboard Scope Plan

- Status: `done`
- Priority: `P2`
- Goal: plan the dashboard views and API needs.
- Acceptance:
  - Covers runs, companies, contacts, evaluations, drafts, send queue, blocked intents, and audit logs.
  - No marketing landing page.
  - Completed by `docs/DASHBOARD_SCOPE_PLAN.md` and `archive/tick-004-001.md`.

### AM-004-002A: Add Read-Only Dashboard APIs

- Status: `done`
- Priority: `P2`
- Goal: add read-only API endpoints for the dashboard MVP.
- Acceptance:
  - Exposes read-only list/detail endpoints for companies, contacts, fit evaluations, email drafts, send intents, gate results, outreach records, and dashboard summary counts.
  - Supports basic filters for status, reason code, confidence, review flags, run, company, contact, and audit fields.
  - Tests cover list/detail/filter behavior.
  - No send endpoint, reservation creation, email adapter, Gmail integration, or OpenAI dependency.
  - Completed by `archive/tick-004-002A.md` and `reviews/tick-004-002A-dashboard-apis.md`.

### AM-004-002B: Build Dashboard MVP

- Status: `done`
- Priority: `P2`
- Goal: implement a local dashboard for inspectability.
- Acceptance:
  - Shows backend state, not agent assumptions.
  - Supports filtering by status/reason/confidence/review flags.
  - Does not expose a send button, reservation action, Gmail integration, email adapter, or OpenAI dependency.
  - Completed by `archive/tick-004-002B.md` and `reviews/tick-004-002B-dashboard-mvp.md`.

## Phase 5: Onboarding Flow

### AM-005-001: Onboarding Data Contract Plan

- Status: `done`
- Priority: `P2`
- Goal: plan onboarding run inputs, outputs, review states, and snapshot promotion.
- Acceptance:
  - Distinguishes verified documents, user claims, inferred information, and needs-review items.
  - Exclusions are learned and stored in `policy.json`.
  - Defines review and promotion rules for `user_profile.json`, `master_cv_profile.json`, and `policy.json`.
  - Completed by `docs/ONBOARDING_DATA_CONTRACT_PLAN.md`, `archive/tick-005-001.md`, and `reviews/tick-005-001-onboarding-data-contract.md`.

### AM-005-002: Onboarding Review Workflow

- Status: `done`
- Priority: `P2`
- Goal: implement review/promotion for `user_profile.json`, `master_cv_profile.json`, and `policy.json`.
- Acceptance:
  - Future CV tailoring uses approved master CV claims only.
  - Unapproved claims cannot be used automatically.
  - Candidate snapshots import as `candidate`.
  - Promotion writes audit logs and marks approved/superseded status deterministically.
  - Completed by `archive/tick-005-002.md` and `reviews/tick-005-002-onboarding-review-workflow.md`.

### AM-005-003: Onboarding Review Schemas

- Status: `done`
- Priority: `P2`
- Goal: add `onboarding_review.json` schema and backend validation model.
- Acceptance:
  - Review items include stable IDs, target file, target JSON pointer, proposed value, provenance, confidence, state, reviewer metadata, and resolution notes.
  - Contradictions and missing required information are first-class review item types.
  - Schema validation rejects hidden side effects and unknown fields.
  - Completed by `archive/tick-005-003.md`.

## Phase 6: Codex Run Orchestration

### AM-006-000: Codex Runtime Bridge ADR

- Status: `done`
- Priority: `P1`
- Goal: document the supported Codex runtime modes, including the tmux-backed interactive onboarding chat and file-output worker runs.
- Context:
  - The application owns long-lived workflow/session state.
  - Onboarding chat uses a long-running interactive Codex session in tmux to simulate a live assistant conversation.
  - Structured non-chat tasks may still use prepared run folders and `codex exec`.
  - Safety-relevant outputs must still be written as structured files and imported through backend validation.
- Acceptance:
  - ADR documents the tmux interactive chat mode for onboarding.
  - ADR distinguishes transcript/session state in the backend from transient Codex process state.
  - ADR defines supported invocation modes: interactive tmux chat for onboarding and file-output worker runs for structured tasks.
  - ADR defines pane startup, trust prompt handling, message routing, output capture, timeout, failure, cancellation, and retry behavior.
  - ADR confirms pane capture is user-facing transcript/log material only and not safety-critical state.
  - ADR confirms all safety-relevant outputs must be written to `output/` files and schema validated before import.
  - ADR confirms Codex receives no secrets, no credentials, no Gmail access, and no send capability.
  - No Gmail, email adapter, send path, OpenAI API dependency, or autonomous action.
  - Completed by `adr/0002-codex-runtime-bridge.md` and `archive/tick-006-000.md`.

### AM-006-001A: Interactive Codex Tmux Chat Adapter

- Status: `done`
- Priority: `P1`
- Goal: implement a backend adapter for sending dashboard onboarding chat messages to a long-running Codex TUI session in tmux.
- Scope:
  - Start or attach to the configured tmux session and pane.
  - Launch plain `codex` when the pane is at a shell prompt.
  - Handle the Codex repository trust prompt for the configured local repository.
  - Send user messages with `tmux set-buffer`, `tmux paste-buffer`, and Enter.
  - Capture pane output and extract/display the newest assistant reply in the dashboard.
  - Persist transcript entries in backend state.
  - Support cancellation and session reset.
- Acceptance:
  - Dashboard can send a message to the tmux Codex session and display the reply.
  - The Codex session remains open across multiple onboarding messages.
  - Backend transcript state is durable and inspectable.
  - The adapter does not send email, call Gmail, mutate safety-critical state, or bypass validation.
  - No OpenAI API dependency is added.
  - Completed by `archive/tick-006-001A.md`.

### AM-006-001: Codex Exec Adapter

- Status: `done`
- Priority: `P2`
- Goal: implement a local backend adapter that can invoke Codex non-interactively for prepared run folders.
- Scope:
  - Add a `CodexRuntimeAdapter` or equivalent service.
  - Invoke `codex exec` with a prepared prompt and run-folder working directory.
  - Capture exit code, stdout, stderr, start timestamp, end timestamp, duration, and failure reason.
  - Persist execution metadata to run logs/audit records.
  - Support configurable timeout.
  - Support a fake runner for tests.
- Acceptance:
  - Adapter can run a prepared Codex task against a run folder.
  - Adapter never passes secrets or send capabilities to Codex.
  - Adapter does not parse safety-critical state from stdout.
  - Adapter treats structured files in `output/` as the only importable agent outputs.
  - Tests cover success, non-zero exit, timeout, missing executable/fake runner, and stdout/stderr capture.
  - No Gmail, email adapter, send path, OpenAI API dependency, or autonomous action.
  - Completed by `archive/tick-006-001.md`.

### AM-006-002: Dashboard Onboarding Chat Page

- Status: `done`
- Priority: `P1`
- Goal: implement a dashboard onboarding page with a chat window backed by the interactive tmux Codex session.
- Context:
  - This is a true long-running local Codex chat session driven through tmux.
  - The backend stores the onboarding session, transcript, uploaded document references, candidate snapshots, and review state.
  - The transcript is durable context for review and finalization, but JSON files remain the importable source of agent output.
- Scope:
  - Add an onboarding chat view to the dashboard.
  - Store each user and Codex message in backend state.
  - Route each user message to the tmux Codex chat adapter.
  - Display captured Codex replies in the chat window.
  - Provide a finish action that sends a finalization instruction to Codex.
  - The finalization instruction asks Codex to write `runs/<run_id>/output/user_profile.json`.
  - Validate candidate `user_profile.json` before import.
- Acceptance:
  - User can complete a conversational onboarding interview in the dashboard.
  - The same Codex TUI session can handle multiple messages in sequence.
  - Backend transcript state survives page refreshes.
  - `user_profile.json` conforms to `schemas/user_profile.schema.json`.
  - Candidate profile output is schema validated and remains unapproved until promoted by the existing review workflow.
  - No automatic promotion happens inside this tick.
  - No Gmail, email adapter, send path, OpenAI API dependency, or autonomous action.
  - Completed by `archive/tick-006-002.md`.

### AM-006-003: Run Folder Generator

- Status: `done`
- Priority: `P2`
- Goal: create backend-supported run folders with `input/`, `output/`, `logs/`, `task.md`, and `instructions.md`.
- Acceptance:
  - Agents receive scoped context only.
  - Secrets and send capabilities are never included.
  - Generated run folders are reproducible and inspectable.
  - Run folders can be used by the Codex exec adapter.
  - Completed by `archive/tick-006-003.md`.

### AM-006-004: Run Import Integration

- Status: `done`
- Priority: `P2`
- Goal: connect generated runs to import and dashboard visibility.
- Acceptance:
  - Every run is reproducible and inspectable.
  - Outputs remain schema validated.
  - Codex execution metadata, validation results, imported records, and failures are visible through the dashboard.
  - No stdout/stderr data is treated as safety-critical state.
  - No Gmail, email adapter, send path, OpenAI API dependency, or autonomous action.
  - Completed by `archive/tick-006-004.md`.

## Phase 7: Email Adapter Interface

### AM-007-001: Fake Adapter Interface Only

- Status: `done`
- Priority: `P3`
- Goal: define an email adapter interface and fake dry-run adapter without real sending.
- Acceptance:
  - Adapter cannot be reached without passed gate and reservation.
  - Real Gmail sending remains unimplemented.
  - Completed by `archive/tick-007-001.md` and `reviews/tick-007-001-fake-adapter-interface.md`.

### AM-007-002: Reservation Preconditions

- Status: `done`
- Priority: `P3`
- Goal: test that future adapter handoff requires `reserve_for_send` and transactional reservation.
- Acceptance:
  - No real send path exists.
  - Tests prove direct adapter invocation is impossible through public APIs.
  - Completed by `archive/tick-007-002.md` and `reviews/tick-007-002-reservation-preconditions.md`.

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



### AM-FUTURE-003: Onboarding Agent Prompt And Run Template

- Status: `done`
- Priority: `P3`

Goal: create the onboarding agent instructions, run template, example input/output fixtures, and sample onboarding transcript flow.

Acceptance:
- Agent asks about experience, projects, education, values, target roles, locations, exclusions, tone, and uploaded documents.
- Agent outputs user_profile.json, master_cv_profile.json, policy.json, and onboarding_review.json.
- Outputs follow schemas and mark provenance/confidence/review state.
- No automatic promotion without backend review workflow.
- Completed by `reviews/AM-006-005_ONBOARDING_RECRUITER_ARTIFACTS.md`.


### AM-FUTURE-004: Company Research Run Template

Goal: create the Codex run template and instructions for company research based on approved profile and policy snapshots.

Acceptance:
- Research agent receives scoped context only.
- Outputs company candidates with sources, fit reasons, risk flags, and policy flags.
- No send intent generation in this tick.
