# Codex Tmux Bridge Plan

> Historical implementation plan retained for diagnostics. Pi RPC is now the single application agent runtime, and this bridge must remain unwired from product workflows.

## Purpose

The tmux bridge is the live local transport between the backend and a signed-in Codex CLI session. It supports the intended product workflow:

1. The user creates or selects a local profile in the app.
2. The backend starts or attaches a Codex tmux session for onboarding.
3. The user chats with a recruiter-like Codex session through the UI.
4. The backend persists the transcript and run metadata as application state.
5. Codex writes structured files under `runs/<run_id>/output/`.
6. The backend validates and imports those files before they affect profiles, campaigns, companies, gates, or later outreach.

The bridge is transport only. It must never send email, call Gmail, call an email adapter, decide gate outcomes, promote profile snapshots, or mutate source-of-truth state outside backend services.

## Current Implementation

The bridge lives in `backend/app/agents/codex_tmux.py`.

It runs tmux commands through WSL:

```text
wsl -d <distro> -- tmux <args>
```

The configured target is represented by `TmuxTarget`:

- `distro`: WSL distro name.
- `session`: tmux session name, default `codex`.
- `window`: tmux window index.
- `pane`: tmux pane index.
- `pane_ref`: `<session>:<window>.<pane>`.

The bridge sends literal prompts through tmux buffers:

```text
tmux set-buffer -t <session> -- <message>
tmux paste-buffer -t <session>:<window>.<pane>
tmux send-keys -t <session>:<window>.<pane> C-m
```

This avoids brittle nested quoting across PowerShell, WSL, shell, tmux, and Codex.

## Available Backend Functions

`TmuxCodexBridge` now supports:

- `start_fresh_session(workdir, kill_existing=True)`: force a clean tmux session and start a shell in the repo.
- `start_fresh_window(workdir, window_name=None)`: create a new tmux window for a separate app run or campaign.
- `attach_app_session(app_session_id, workdir, fresh=False)`: associate an app run/session ID with a tmux target and return attachment metadata.
- `start_interactive_codex(workdir)`: launch plain `codex` in the target pane.
- `send_chat_message(message)`: paste and submit live chat input.
- `start_codex_exec(...)`: paste a `codex exec` command for structured file-output runs when that mode is appropriate.
- `capture_pane(start_line=-200)`: read visible pane output.
- `capture_snapshot(...)` and `read_new_output(previous, ...)`: capture output and best-effort incremental output since the prior capture.
- `pane_command()`: inspect the current tmux pane command.
- `is_alive()`: verify the tmux session and pane are reachable.
- `list_sessions()`: list tmux sessions for operator/debug visibility.
- `close_session_gracefully()`: send cancel and `exit`.
- `force_kill_session(missing_ok=False)`: kill a stale tmux session when graceful close is not enough.
- `reset_to_shell(workdir)`: respawn the target pane at a shell prompt.

`backend/app/agents/onboarding_chat.py` wraps the bridge for onboarding:

- Persists user and assistant transcript entries to `runs/<run_id>/logs/onboarding_chat.jsonl`.
- Sends the recruiter prompt once per onboarding run and records that as a system event instead of a user chat message.
- Records tmux attachment metadata as a system transcript event.
- Provides liveness/session listing helpers for backend use.
- Logs cancellation, reset, graceful close, and force-kill events.

## Source Of Truth

Backend-owned state remains authoritative:

- Users and selected profiles.
- Profile, master CV, and policy snapshots.
- Onboarding sessions and transcripts.
- Campaigns and campaign run records.
- Imported companies, contacts, fit evaluations, drafts, send intents, gate results, reservations, outreach records, and audit logs.

Tmux/Codex process memory is not authoritative. Pane capture is display/log material only. Importable state must come from files in `output/`, pass schema validation in `schemas/`, and be normalized by backend services.

## Product Use Cases

### Onboarding Chat

Use a long-running interactive Codex session in tmux.

The backend should:

- Create or select a profile shell.
- Create an onboarding run/session record.
- Create a fresh run-specific tmux window/pane for the app session. If the base tmux session already exists, reuse it as the container instead of trying to recreate it.
- Launch `codex` if needed.
- Send the onboarding recruiter prompt once, with artifact paths and schema boundaries.
- Send user chat messages through `send_chat_message`.
- Persist every user message, assistant capture, transport error, cancellation, and reset.
- On finish, send a finalization prompt that asks Codex to write `user_profile.json`, `master_cv_profile.json`, `policy.json`, and `onboarding_review.json` under `runs/<run_id>/output/`.
- Import the files through the existing validation pipeline.
- After successful validation/import, gracefully close and then kill only the run-specific tmux window/pane. Do not kill the shared base tmux session unless explicitly requested for stale-session cleanup.

### Campaign Research

Use a campaign-specific tmux session/window when the user starts a regional job-search campaign.

The backend should:

- Persist the campaign before launching Codex.
- Generate a run folder with scoped approved profile/policy context.
- Start a fresh tmux window named from the campaign/run ID.
- Send the research task prompt.
- Periodically capture output for logs only.
- Import `company_candidate.json` and later related outputs from `output/`.
- Keep found companies in backend tables as reviewable candidates.

## Failure Handling

Failures must be represented in backend state and logs:

- WSL unavailable.
- tmux unavailable.
- session/window/pane missing.
- Codex not running.
- trust prompt unresolved.
- send timeout.
- capture failure.
- stale or wedged tmux session.
- expected output missing.
- schema validation failure.

Allowed recovery actions:

- Reattach to the existing session.
- Reset pane to shell.
- Start a fresh session/window.
- Gracefully close the session.
- Force-kill stale sessions when explicit backend action requires it.

None of these actions may approve data, pass a gate, reserve a send, or send email.

## Next Implementation Work

1. Add database-backed profile shell and user selection state.
2. Make onboarding sessions first-class backend records instead of transcript-file-only state.
3. Add campaign records and campaign creation UI.
4. Add campaign research run launch using a campaign tmux window.
5. Add company import/review/detail views as the primary product surface.
6. Keep run logs, validation results, gate results, send queue, and audit logs in Developer Logs navigation.
