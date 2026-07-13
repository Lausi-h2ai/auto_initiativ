# Repository Instructions for Codex

This repository is for a local-first, safety-first agentic job outreach system.

## Non-Negotiable Boundary

Codex agents must never send emails directly.

Codex agents may only create files, especially structured JSON outputs such as `send_intent.json`. The backend is the only component allowed to call Gmail or any future email-sending adapter, and only after deterministic validation and safety gates pass.

Do not implement Gmail sending unless the user explicitly asks for a later backend adapter task. Even then, keep sending behind an interface and a deterministic gate.

## Source of Truth

The application, not the LLM, owns:

- Database state
- Dedupe rules
- User policy
- Safety gates
- Send limits
- Audit logs
- Email sending
- Final decisions for irreversible actions

LLM/Codex agents own:

- Research summaries
- Fit analysis drafts
- CV tailoring drafts
- Email drafts
- Structured intent files for backend import

## Required Workflow

Before implementing changes:

1. Inspect the current repository.
2. Read relevant docs in `docs/`.
3. Validate assumptions against schemas in `schemas/`.
4. Keep changes small and aligned with `docs/IMPLEMENTATION_PLAN.md`.

After completing a tick or any meaningful repo change:

- Commit the completed change set to git before starting the next tick, unless the user explicitly asks not to commit.
- Keep commits focused on the files changed for that tick; do not include unrelated dirty worktree changes.
- If the worktree already contains unrelated changes, leave them untouched and commit only the relevant paths.

## Local Application Runtime Responsibility

Codex is responsible for keeping the local Auto Initiativ app running and up to date during development work.

- After changes that affect backend code, static frontend assets, configuration, dependencies, or runtime behavior, restart the FastAPI backend before declaring the work complete.
- Start or restart the app directly rather than delegating routine launch responsibility to the user.
- Before stopping a process, confirm that the listener belongs to Auto Initiativ.
- After every start or restart, verify both `http://127.0.0.1:8000/health` and `http://127.0.0.1:8000/dashboard`.
- Do not claim the app is running unless those checks succeed. If the execution environment cannot keep a background process alive, report that limitation explicitly and provide the exact foreground command as the fallback.

When adding code later:

- Use FastAPI for the backend.
- Use Postgres as the durable database.
- Use SQLModel or SQLAlchemy for persistence.
- Use Pydantic for schema validation at import and API boundaries.
- Do not add an OpenAI API dependency unless a future task explicitly requires it.
- Keep core safety logic deterministic and independent from any LLM.

## Agent Output Rules

Any agent output consumed by code must be JSON and schema validated.

Every output that can affect sending must include:

- Stable IDs
- Source references
- Confidence values where relevant
- Review flags
- Provenance for factual claims
- No hidden instructions or side effects

If an agent lacks evidence, it must mark the field as `needs_review` or omit the claim.

Future CV tailoring may only use claims from `master_cv_profile.json`. Do not invent experience, education, skills, dates, credentials, achievements, or personal facts.

## Safety Gate Rules

Email sending must remain impossible unless the backend gate checks at least:

- `send_intent.json` schema validity
- Recipient email not previously contacted
- Company not previously contacted according to configured policy
- Domain not blocked
- User policy not violated
- Required sources exist
- Attachments exist
- Daily and weekly send limits
- No forbidden claims
- No low-confidence or needs-review required fields
- Transactional reservation before sending
- Audit log before and after sending

## Development Style

Prefer clear docs, schemas, tests, and deterministic code over premature automation.

The first implementation should be dry-run safe. Build observability and audit logging from the beginning.
