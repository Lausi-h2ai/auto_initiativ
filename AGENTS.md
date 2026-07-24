# Repository Instructions for Codex

Auto Initiativ is a local-first, safety-first agentic job-outreach system.

## Safety and Authority

- Codex agents must never send email directly. They may create drafts and structured intent files; only the backend may call an email adapter after deterministic validation and safety gates pass.
- Do not implement real Gmail sending unless the user explicitly requests that backend-adapter task. Keep it behind an interface, deterministic gate, transactional reservation, and audit logging.
- The application—not an LLM—owns database state, dedupe, policy, limits, gates, audit logs, sending, and irreversible decisions.
- LLM/Codex work is limited to research and fit summaries, CV and email drafts, and structured files for backend import.
- Code-consumed agent output must be JSON and schema validated, with stable IDs, sources, confidence where relevant, review flags, and factual provenance. Missing evidence must be omitted or marked `needs_review`.
- CV tailoring may use only claims in `master_cv_profile.json`; never invent personal facts, credentials, dates, skills, or achievements.

## Implementation Workflow

Only when a task requires repository changes:

1. Inspect the directly relevant code and current worktree.
2. Read only the documentation in `docs/` that directly governs the change; do not bulk-read the directory.
3. Inspect only the schemas in `schemas/` that govern changed inputs, outputs, or API boundaries. If no schema is implicated, state that and continue.
4. Keep the change small and consistent with `docs/IMPLEMENTATION_PLAN.md`.

Prefer deterministic code, clear schemas, tests, observability, and dry-run safety over premature automation.

After a completed tick or meaningful repository change, commit only its relevant paths before starting another tick unless the user asks not to commit. Preserve unrelated worktree changes.

## Workflow Graph Architecture

- Treat `adr/0003-application-owned-workflow-graph.md` as the governing decision for graph orchestration.
- Keep graph definitions trusted, code-owned, versioned, and validated through `backend/app/workflow/graph.py`.
- Keep Postgres and application domain rows authoritative. Do not introduce a framework checkpoint, agent memory, run-folder file, or mutable graph-state blob as a second source of truth.
- Keep Pi RPC as the restricted file-producing agent runtime unless a separate, explicit architecture decision changes it. Do not introduce LangGraph, the OpenAI Agents SDK, or another orchestration runtime merely to execute the existing graph definitions.
- Only registered deterministic backend predicates may choose edges. Agent output may contribute schema-valid evidence but must never name a destination, allocate shared budget, declare coverage, approve work, or modify topology.
- Pin every graph run to a stable definition ID and version. Never silently migrate an active run to a newly deployed definition.
- Give every node execution a stable, workspace-scoped execution key. Downstream materialization and replay must be idempotent.
- Bound every cycle by attempts, elapsed time, or application-owned budget, and test that the bound is enforced at runtime rather than merely declared.
- Claim queued work atomically. Respect worker lease ownership, reconcile expired external work before taking action, and block uncertain launch/provider outcomes instead of relaunching automatically.
- Keep privileged sending as a separate facade. No generic graph executor or agent node may call an email adapter. Every provider path must preserve the ordered validation, authorized approval snapshot, evaluate-only gate, transactional reservation, and audit checkpoints.
- `coordinated_research` v1 remains shadow-observed until mismatch evidence is reviewed and an explicit cutover tick is approved. `application_preparation` v1 and `privileged_sending` v1 are static validated boundaries, not authorization to replace their existing services.
- For graph changes, add topology, transition-table, bounded-cycle, workspace-isolation, replay/idempotency, crash-recovery, and privileged-path tests as applicable. SQLite tests do not prove PostgreSQL locking or concurrency behavior.

## Runtime

- Follow any closer `AGENTS.md` instructions when working within a subtree.
- After changes to backend code, built frontend assets, configuration, dependencies, or runtime behavior, restart the FastAPI app directly.
- Before stopping a listener, confirm it belongs to Auto Initiativ. After starting, verify both `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/dashboard`; otherwise report the limitation and exact foreground command.

## Sending Gate Minimum

Sending must remain impossible unless the backend deterministically confirms schema validity, recipient and company dedupe, allowed domain and policy, required sources and attachments, daily and weekly limits, absence of forbidden or review-blocked claims, a transactional reservation, and audit records before and after the attempt.
