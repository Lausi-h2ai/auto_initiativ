# Codex Tmux Bridge

This project can drive a signed-in Codex CLI session through a WSL tmux pane for local-first agent work.

## Working Smoke Test

On this machine, the reachable setup is:

- WSL distro: `Ubuntu-24.04-bonsai-vllm`
- tmux session: `codex`
- pane: `codex:0.0`
- repo path in WSL: `/mnt/f/auto_initiativ`

The successful smoke test was:

```bash
cd /mnt/f/auto_initiativ && codex exec --ephemeral --sandbox read-only \
  -o /tmp/auto_initiativ_codex_smoke.txt \
  'Reply with exactly: TMUX_CODEX_SMOKE_OK'
```

Codex wrote `TMUX_CODEX_SMOKE_OK` to `/tmp/auto_initiativ_codex_smoke.txt`.

## Recommended Use

Use two modes:

- Interactive onboarding chat: start or attach to an interactive Codex session in tmux, send user messages with `tmux set-buffer` plus `tmux paste-buffer`, and return visible output with `tmux capture-pane`.
- Structured task execution: prefer `codex exec` with `-o` and, when applicable, `--output-schema` so the backend can import files from `runs/<run_id>/output/`.

The official Codex automation path is `codex exec`. It supports final-message file output with `-o`, JSONL event output with `--json`, and schema-constrained final output with `--output-schema`.

## Interactive Onboarding Chat

The tmux transport has been validated for a live Codex TUI session:

- Start `codex` in the pane.
- Accept the repository trust prompt when needed.
- Send chat messages with `tmux set-buffer`, `tmux paste-buffer`, and Enter.
- Capture replies with `tmux capture-pane`.
- Keep the Codex session open between messages so the user experiences a continuous chat.

The working Python transport shape is:

```python
def send_tmux_message(message: str) -> None:
    tmux("set-buffer", "-t", "codex", "--", message)
    tmux("paste-buffer", "-t", "codex:0.0")
    tmux("send-keys", "-t", "codex:0.0", "C-m")
```

For onboarding, the session starts with a recruiter prompt that instructs Codex to write candidate artifacts under `runs/<run_id>/output/`: `user_profile.json`, `master_cv_profile.json`, `policy.json`, and `onboarding_review.json`. The backend then validates and imports those files as candidate/unapproved state. The transcript and captured pane output are useful for review and debugging, but they are not authoritative application state.

## Safety Boundaries

The tmux bridge is transport only. It must not:

- Send email.
- Call Gmail or any email adapter.
- Mutate the database directly.
- Decide that a safety gate passed.
- Bypass schema validation or import audit logs.

Agent outputs that affect later steps must still be written as JSON, validated against `schemas/`, imported by the backend, and reviewed or gated deterministically.

## Implementation Notes

Use `backend.app.agents.codex_tmux.TmuxCodexBridge` for process control. It uses `tmux set-buffer` and `tmux paste-buffer` instead of raw nested shell quoting, because nested PowerShell, WSL shell, tmux, and prompt strings are otherwise easy to mangle.

The bridge is covered by mocked tests and does not require WSL, tmux, or Codex during normal test runs.
