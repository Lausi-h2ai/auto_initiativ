# Agent Brief

Last updated: 2026-05-15

## Operating Context

This repository is a local-first, safety-first agentic job outreach system. The backend owns database state, deterministic safety gates, dedupe, policy enforcement, send limits, audit logs, and any future irreversible actions.

Agents may produce research, fit analysis, CV tailoring drafts, email drafts, and structured intent files. Agents must not send email directly.

## Current Phase

Current phase: safe agent run templates after Phase 7 fake adapter/reservation preconditions.

Completed foundations:

- Phase 1 backend skeleton, schema-backed import, validation, and audit persistence.
- Phase 2 normalized domain persistence and deterministic dedupe constraints.
- Phase 3 deterministic `evaluate_only` safety gate.
- Phase 4 read-only dashboard APIs and backend-served dashboard MVP.
- Tmux-backed interactive onboarding chat with dashboard UI and user-profile-only candidate import.
- Non-interactive Codex exec adapter with execution logs and audit metadata.
- Deterministic run-folder generator for scoped Codex exec tasks.
- Generated-run integration path from run folder to Codex exec to schema-backed import and dashboard-readable state.
- Private fake dry-run email adapter interface guarded by reserved gate and reservation preconditions.
- Private `reserve_for_send` reservation precondition service that creates `SendReservation` records without adapter handoff.

## Current Recommended Tick

`AM-FUTURE-003: Onboarding Agent Prompt And Run Template`

Goal: create the onboarding agent instructions, run template, example input/output fixtures, and sample onboarding transcript flow.

Required constraints:

- Keep agent outputs file-based and schema validated.
- Do not add Gmail, SMTP, external sending service integration, or network send behavior.
- Do not add a public send endpoint.
- Do not automatically promote onboarding snapshots.
- Use approved schemas and review workflow for `user_profile.json`, `master_cv_profile.json`, `policy.json`, and `onboarding_review.json`.
- Continue to preserve the non-negotiable boundary: Codex agents never send emails directly.

## Relevant Context

- Runtime decision: `adr/0002-codex-runtime-bridge.md`.
- Tmux bridge notes and smoke-test details: `docs/CODEX_TMUX_BRIDGE.md`.
- Existing exec adapter: `backend/app/agents/codex_exec.py`.
- Existing run folder generator: `backend/app/agents/run_folder.py`.
- Existing generated-run integration: `backend/app/agents/codex_run.py`.
- Existing process-control helper for tmux chat: `backend/app/agents/codex_tmux.py`.
- Existing run import path: `backend/app/imports/import_service.py`.
- Company research runs are intended to find profile-aligned companies and public career contact emails during the same crawl; they do not need open job listings.
- The company research agent may write `company_candidate`, `contact_candidate`, and `fit_evaluation` JSON artifacts, but must not write drafts, send intents, Gmail output, or outreach instructions.
- Deterministic gate: `backend/app/gates/evaluate_only.py`.
- Reservation precondition service: `backend/app/gates/reserve_for_send.py`.
- Fake dry-run email adapter and preconditioned handoff service: `backend/app/email_delivery/`.
- Existing audit models and route patterns: `backend/app/db/models.py`, `backend/app/api/routes.py`.
- Dashboard onboarding chat was completed by `archive/tick-006-002.md`.
- Codex exec adapter was completed by `archive/tick-006-001.md`.
- Run folder generator was completed by `archive/tick-006-003.md`.
- Run import integration was completed by `archive/tick-006-004.md`.

## Safety Notes

- Future CV tailoring may only use approved claim IDs from an immutable `master_cv_profile.json` snapshot.
- If onboarding evidence is missing, contradictory, low-confidence, inferred, or policy-relevant, the output must mark it for review rather than silently promote it.
- Snapshot promotion must be deterministic backend behavior, not an LLM decision.
