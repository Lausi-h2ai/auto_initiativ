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
- Check user policy, blocked domains, blocked recipients, company dedupe, contact dedupe, source existence, attachment existence, limits, forbidden claims, and review flags.
- Create `gate_result` records.
- Write audit logs before and after gate evaluation.
- Keep gate output deterministic and testable.

Acceptance:

- Gate decisions are explainable.
- All risky or missing data blocks by default.
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
- Add a dashboard onboarding page with a chat window backed by a long-running interactive Codex session in tmux.
- Route user chat messages from the dashboard to the tmux Codex session and return captured Codex replies to the dashboard.
- Accept uploaded career documents as local files.
- Start the chat with recruiter instructions that tell the tmux Codex session how to interview and where to write candidate artifacts.
- At the end of the chat, instruct the tmux Codex session to write `runs/<run_id>/output/user_profile.json`, `master_cv_profile.json`, `policy.json`, and `onboarding_review.json` matching their schemas.
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
- Add a tmux Codex session transport for interactive onboarding chat, including start, send-message, capture-output, finalize-output, timeout, and cancellation behavior.
- Import `output/` after completion.
- Store run logs and audit entries.

Acceptance:

- Interactive Codex chat is transport only; the backend remains the source of truth for transcript, run state, validation, and promotion.
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
