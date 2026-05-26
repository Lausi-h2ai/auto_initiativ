# AM-006-004 Profile Shell And Onboarding Chat UX

## Scope

Built the first product-facing setup journey for the local personal recruiter app. The app now opens on a Profile page that shows whether an approved user profile exists and, when it does not, gives the user a direct path into the tmux-backed Codex onboarding chat.

## Changes

- Added `GET /profile/summary` to report approved and candidate profile snapshot state.
- Added explicit onboarding session state persisted under `runs/<run_id>/logs/onboarding_session.json`.
- Added onboarding chat status/action APIs:
  - `GET /onboarding/chat/{run_id}/status`
  - `POST /onboarding/chat/{run_id}/refresh`
  - `POST /onboarding/chat/{run_id}/close`
  - `POST /onboarding/chat/{run_id}/reset`
- Updated start/message responses to include backend session state.
- Recorded tmux failures as failed backend session state and transcript system events.
- Added a Profile page as the first dashboard section.
- Added visible session states for `not_started`, `running`, `waiting`, `failed`, and `closed`.
- Added UI controls for Start Onboarding, Read Output, Reset, and Close.
- Kept runs, gate results, send queue, outreach history, and audit logs grouped under Developer Logs.

## Boundary Review

No Gmail sending, real email adapter sending, OpenAI API dependency, autonomous sending, campaign workflow, or gate bypass was added.

Codex/tmux state remains transport/process state. Backend-owned profile snapshots, onboarding session files, transcripts, validation results, promotion state, gates, and audit logs remain authoritative. Pane output is displayed and logged, but it is not imported as source-of-truth profile data unless Codex writes schema-valid files and the backend import path validates them.

## Tests

Command run:

```powershell
uv run --python 3.12 --extra test pytest backend/tests/test_onboarding_chat_adapter.py backend/tests/test_onboarding_chat_api.py backend/tests/test_dashboard_ui.py backend/tests/test_onboarding_promotion.py
```

Result: 26 passed in 11.99s.

Additional adjacent verification:

```powershell
uv run --python 3.12 --extra test pytest backend/tests/test_codex_tmux_bridge.py backend/tests/test_onboarding_chat_adapter.py backend/tests/test_onboarding_chat_api.py backend/tests/test_dashboard_ui.py backend/tests/test_dashboard_api.py backend/tests/test_boundaries.py
```

Result: 49 passed in 20.99s.

Full backend verification:

```powershell
uv run --python 3.12 --extra test pytest
```

Result: 225 passed, 1 skipped in 138.78s.

## Follow-Up

The next tick should move onboarding session state from file-backed JSON into first-class database records tied to the active profile shell. Campaign creation remains intentionally out of scope for this tick.
