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

## Runtime

- Follow any closer `AGENTS.md` instructions when working within a subtree.
- After changes to backend code, built frontend assets, configuration, dependencies, or runtime behavior, restart the FastAPI app directly.
- Before stopping a listener, confirm it belongs to Auto Initiativ. After starting, verify both `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/dashboard`; otherwise report the limitation and exact foreground command.

## Sending Gate Minimum

Sending must remain impossible unless the backend deterministically confirms schema validity, recipient and company dedupe, allowed domain and policy, required sources and attachments, daily and weekly limits, absence of forbidden or review-blocked claims, a transactional reservation, and audit records before and after the attempt.
