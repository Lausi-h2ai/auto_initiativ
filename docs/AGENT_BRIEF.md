# Agent Brief

Last updated: 2026-07-24

## Operating Context

Auto Initiativ is a local-first, safety-first system for initiative outreach and listed-job application preparation. The backend owns database state, workspace isolation, dedupe, policy, limits, gates, reservations, audit logs, provider calls, and every irreversible decision.

Agents may produce sourced research, fit analysis, CV and cover-letter drafts, email drafts, and schema-valid structured files. Agents never send email, submit application forms, access provider credentials, approve work, allocate shared budgets, or choose workflow transitions.

## Current Phase

The original Phases 1–7 are complete. The current phase is coordinated-research workflow-graph hardening while authoritative execution remains in the existing workflow engine.

Completed foundations include:

- Schema-backed import, normalized persistence, deterministic dedupe, and audit history.
- Deterministic evaluate-only and reservation gates.
- Guided onboarding with restricted Pi RPC, durable transcript, candidate review, and explicit snapshot promotion.
- Coordinated initiative and listed-job research with confirmed plans, target coverage, shared budgets, scope filtering, and deterministic ranking.
- Claim-grounded application packages and a dedicated Master CV builder with deterministic rendering, portrait handling, immutable approval, export, and campaign pinning.
- English and `de-DE` workspace localization.
- Backend-only Gmail delivery guarded by explicit configuration, authorized approval, deterministic checks, transactional reservation, and audit checkpoints.
- Trusted workflow definitions, topology checks, task correlation, atomic claims, lease recovery, uncertain-launch blocking, and aggregate shadow-readiness reporting.

## Current Recommended Tick

Collect the missing shadow scenarios and database proofs listed in `docs/WORKFLOW_GRAPH_SHADOW_READINESS.md`.

Required outcomes:

- Observe both initiative-outreach and listed-job campaign kinds through the complete graph path.
- Cover shared-budget allocation/exhaustion and multi-target fan-in.
- Run the competing-worker, execution-key, and lease tests against disposable PostgreSQL.
- Complete the remaining crash-recovery and workspace-cancellation proofs.
- Regenerate the aggregate readiness report.

Do not cut over coordinated research unless the report becomes `ready` and a separate explicit cutover tick is approved.

## Runtime and Architecture

- Pi RPC is the restricted runtime for onboarding, research, verification, Master CV, and application-drafting agents.
- Postgres/application domain rows remain authoritative; run folders and agent sessions are not workflow state.
- Agent JSON is untrusted until schema validation and backend import succeed.
- Graph definitions are trusted, code-owned, versioned, and validated through `backend/app/workflow/graph.py`.
- Only registered deterministic predicates may choose edges.
- `application_preparation` v1 and `privileged_sending` v1 are static validated boundaries, not authorization for dispatcher cutover.
- Tmux and direct Codex-exec adapters remain developer diagnostics and legacy-test surfaces only.

## Safety Notes

- CV and user-descriptive outreach content may use only approved claim IDs from immutable profile snapshots.
- Missing, contradictory, inferred, or low-confidence evidence must be omitted or marked `needs_review`.
- Snapshot and document approval is deterministic backend behavior initiated by an authorized user.
- Listed-job application packages are always submitted manually.
- Provider `outcome_uncertain` blocks and remains reservation-protected; it is never retried automatically.
- No generic graph executor or agent node may call an email adapter.
