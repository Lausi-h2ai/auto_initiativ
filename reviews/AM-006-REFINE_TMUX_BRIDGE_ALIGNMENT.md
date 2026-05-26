# AM-006-REFINE Tmux Bridge Alignment Review

## Scope

This tick realigned the product direction toward a local personal AI recruiter workflow and refined the existing Codex tmux bridge instead of replacing it with a generic batch execution architecture.

## Changes

- Documented the bridge lifecycle and product use in `docs/CODEX_TMUX_BRIDGE_PLAN.md`.
- Documented the product workflow realignment in `docs/PRODUCT_REALIGNMENT_PLAN.md`.
- Extended `backend/app/agents/codex_tmux.py` with session/window lifecycle helpers, liveness checks, session listing, app-session attachment metadata, incremental output capture, graceful close, and force kill.
- Extended `backend/app/agents/onboarding_chat.py` with app-session attachment logging and close/liveness/list helpers.
- Updated onboarding chat start to record tmux attachment metadata when the concrete adapter supports it.
- Adjusted dashboard navigation so onboarding and review surfaces are primary while runs, queue, gate results, history, and audit logs sit under Developer Logs.
- Updated the backlog to make the next ticks profile, onboarding, campaigns, campaign research, company import/detail, and later gated outreach.

## Safety Review

No Gmail sending, real email adapter sending, autonomous sending, or OpenAI API dependency was added.

The bridge remains transport-only. Pane capture and transcripts are still logs/review context, not safety-critical source-of-truth state. Structured outputs must still be written under `runs/<run_id>/output/`, validated against `schemas/`, imported by backend services, and reviewed or gated deterministically.

Existing gate, reservation, dedupe, and audit infrastructure was not removed.

## Tests

Focused tests were added/updated for:

- tmux session/window lifecycle commands.
- liveness and session listing.
- app-session attachment metadata.
- incremental pane output reads.
- graceful close and force-kill behavior.
- onboarding adapter transport lifecycle logging.

Test command run:

```powershell
uv run --python 3.12 --extra test pytest backend/tests/test_codex_tmux_bridge.py backend/tests/test_onboarding_chat_adapter.py backend/tests/test_onboarding_chat_api.py backend/tests/test_dashboard_ui.py
```

Result: 32 passed in 4.05s.

## Follow-Up Risks

- Onboarding sessions are still mostly transcript-file-backed; they should become first-class database records.
- Campaigns are not yet modeled as backend source-of-truth records.
- The dashboard shell still has MVP table ergonomics; future ticks should add profile/campaign/company-specific views without deleting Developer Logs.
- Reply extraction from tmux capture is best-effort and should remain non-authoritative.
