# Implementation Plan

The plan is split into small Codex-friendly phases. Each phase should leave the repository runnable or at least internally consistent.

## Phase 0: Foundation

Status: complete in this repository foundation.

- Create product and architecture docs.
- Define agent boundaries.
- Define safety gate requirements.
- Define onboarding requirements.
- Define JSON schemas.
- Add repository `AGENTS.md`.
- Do not implement sending code.

## Phase 1: Backend Skeleton

Goal: create a dry-run backend that can validate and import files while persisting only minimal operational records.

Phase 1 should not build full domain persistence for companies, contacts, evaluations, drafts, profiles, policies, or send intents. It should store only the records needed to observe and debug imports:

- Runs
- Imported files
- Validation results
- Import audit events
- Basic file metadata and error details

Full normalized domain persistence belongs to Phase 2.

Tasks:

- Add a FastAPI app skeleton.
- Add configuration with explicit `DRY_RUN=true` default.
- Add Pydantic models matching `schemas/`.
- Add JSON schema validation tests.
- Add an import service that reads a run `output/` folder.
- Persist minimal run, import, validation, and audit records to a local development database.
- Add audit logging for imports and validation failures.

Acceptance:

- Invalid agent outputs are rejected with clear errors.
- Imported file status and validation errors are visible through API endpoints.
- Domain records are not yet normalized into full application tables.
- No email adapter exists yet.

## Phase 2: Database Model and Dedupe

Goal: make Postgres the source of truth for outreach state.

Tasks:

- Define SQLModel or SQLAlchemy models.
- Add migrations.
- Add unique constraints for recipient email, company policy key, company domain, and send reservations.
- Add normalized audit log tables.
- Add seed fixtures for local development.

Acceptance:

- Duplicate recipients and duplicate companies cannot be inserted when policy forbids them.
- Dedupe does not depend on prompts.

## Phase 3: Deterministic Gate

Goal: implement the dry-run safety gate.

Tasks:

- Validate `send_intent` records against schema and database state.
- Check user policy, blocked domains, blocked recipients, company dedupe, contact dedupe, source existence, attachment existence, limits, forbidden claims, and blocking review flags.
- Create `gate_result` records.
- Write audit logs before and after gate evaluation.
- Keep gate output deterministic and testable.

Acceptance:

- Gate decisions are explainable.
- Risky or missing data blocks when it cannot be remediated automatically; otherwise it produces an auditable agent-remediation signal.
- Gate tests cover every blocking reason.
- Still no sending code.

## Phase 4: Dashboard MVP

Goal: make agent work observable.

Tasks:

- Build dashboard views for runs, companies, contacts, evaluations, drafts, send queue, blocked intents, and audit logs.
- Add filters for status, blocked reason, confidence, and review flags.
- Add settings views for policy, limits, and blocked domains.

Acceptance:

- User can inspect what happened, what is pending, and what was blocked.
- User can understand why a send intent did or did not pass.

## Phase 5: Onboarding Flow

Goal: create profile and policy source files through a guided process.

Tasks:

- Implement an onboarding run type.
- Add a dashboard onboarding page with a chat window backed by a resumable Pi RPC session.
- Route user chat messages through Pi RPC and return structured assistant replies to the dashboard.
- Accept uploaded career documents as local files.
- Start the chat with recruiter instructions in a run-specific Pi workspace that define how to interview and where to write candidate artifacts.
- At the end of the chat, instruct the Pi agent to write `runs/<run_id>/output/user_profile.json`, `master_cv_profile.json`, `policy.json`, and `onboarding_review.json` matching their schemas.
- Distinguish verified facts, user claims, inferred information, and needs-review items.
- Add review UI for accepting or correcting onboarding outputs.

Acceptance:

- The user can complete a conversational onboarding interview in the dashboard.
- The chat transcript is persisted by the backend and is not treated as validated profile state.
- `user_profile.json` is imported only after schema validation and remains a candidate snapshot until review/promotion.
- CV tailoring can only use approved master CV claims.
- Exclusion criteria are user-learned and stored in `policy.json`.

## Phase 6: Agent Run Orchestration

Goal: prepare repeatable Codex run folders.

Tasks:

- Add run folder creation.
- Generate `task.md` and `instructions.md` from templates.
- Copy validated context into `input/`.
- Use the centralized restricted Pi RPC transport for interactive onboarding, including start, send-message, structured response extraction, resume, finalize-output, timeout, and cancellation behavior.
- Import `output/` after completion.
- Store run logs and audit entries.

Acceptance:

- Interactive Pi chat is transport only; the backend remains the source of truth for transcript, run state, validation, and promotion.
- Final onboarding files written by Codex are treated exactly like other agent outputs and must pass schema validation before import.
- Each agent run is reproducible and inspectable.
- Backend never trusts output without validation.

## Phase 7: Email Adapter Interface

Goal: prepare for future sending without enabling it by default.

Tasks:

- Define an email adapter interface.
- Add a fake dry-run adapter.
- Add integration tests proving the gate is required before adapter invocation.
- Keep real Gmail sending unimplemented unless explicitly requested.
- Keep `sent` and `send_failed` as future send result statuses, not safety gate statuses.

Acceptance:

- Adapter cannot be reached without a passed gate result and transactional reservation.
- Dry-run remains the default.

## Next Recommended Codex Task

Implement Phase 1: create a minimal FastAPI backend skeleton with Pydantic models generated from or aligned to the schemas, a dry-run configuration default, and an import service that validates JSON files from a run `output/` folder. Persist only minimal run, import, validation, and audit records. Do not implement normalized domain persistence yet. Do not add Gmail sending.

## Listed Job Campaign Extension

Status: implemented as a parallel campaign path.

- `initiative_outreach` remains backward-compatible.
- `listed_job_search` uses the Vacancy Scout, job-specific schemas, deterministic verification states, manual refresh, and a separate Jobs UI.
- New company and vacancy campaigns first persist a versioned, schema-validated research plan for user confirmation.
- Confirmed plans run one target-scoped research task per location or remote region, with equal source-category attempt quotas and explicit covered, exhausted, and failed states.
- Bare `Remote` is normalized to fully remote within Europe. Explicit scope conflicts are excluded by the backend; missing evidence is retained with a review marker.
- Additional search guidance is passed to both research paths and remains distinct from backend-owned hard constraints.
- The dashboard shows the interpreted plan and per-target attempts, candidate counts, and retained counts.
- Employer pages may be discovered dynamically; configured trust affects whether evidence can establish `verified_open`, not whether a source may be searched.
- Application packages are schema validated, use only approved master-CV claims, require a fresh verified vacancy, and are always submitted manually by the user.

## Master CV Builder Extension

Status: implementation in progress. The governing design is in `docs/MASTER_CV_BUILDER.md`.

- Add a dedicated Master CV workspace without increasing onboarding's required steps.
- Vendor the MIT-licensed resume-builder skill and adapt all thirteen templates through application-owned, A4-safe adapters.
- Treat portraits as first-class profile assets from the first release, including German and Swiss market defaults.
- Persist candidate and approved document versions separately from the approved factual claim ledger.
- Use one restricted Pi RPC specialist for iterative design and content proposals; validate all code-consumed output as JSON.
- Keep approval, rendering, assets, provenance, and downstream version pinning deterministic and application-owned.

## Workspace Localization Extension

Status: implemented for English and `de-DE`.

- Persist a canonical locale per workspace and expose it through authenticated workspace preferences.
- Use a central locale registry and semantic frontend message catalogs so later locales can be added without distributed language branches.
- Pin output locale in agent-run metadata and prompts while keeping application-document language context-aware and separately configurable.
- Preserve historical, user-authored, and external source text in its original language.
