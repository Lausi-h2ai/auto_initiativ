# ADR-0002: Codex Runtime Bridge

## Status

Accepted

## Context

The application needs to use Codex as a local agent runtime without adding an OpenAI API dependency to the backend. Two runtime shapes are needed:

- A live onboarding conversation in the dashboard, where the user expects a continuous chat experience.
- Structured agent work that reads prepared run folders and writes schema-validated output files.

The current local experiment validated that a signed-in Codex TUI can run inside WSL tmux and can receive messages through `tmux set-buffer`, `tmux paste-buffer`, and Enter. Pane capture can retrieve the visible reply, while the session stays open for later messages.

OpenAI's Codex documentation identifies `codex exec` as the non-interactive mode for scripts and CI-style jobs. It also documents machine-readable JSONL output, final-message file output with `-o`, and schema-constrained final output with `--output-schema`. The same CLI reference covers the base `codex` command and global flags for interactive sessions.

References:

- `https://developers.openai.com/codex/noninteractive`
- `https://developers.openai.com/codex/cli/reference#codex-exec`
- `https://developers.openai.com/codex/cli/reference#global-flags`

## Decision

Support two Codex runtime modes.

### 1. Interactive tmux chat mode

Use this mode only for dashboard onboarding chat.

The backend starts or attaches to a configured WSL tmux session and pane, launches plain `codex` when needed, handles the repository trust prompt for the configured local repository, routes user messages into the pane, captures assistant replies, and persists transcript entries in backend state.

The transport sequence is:

```text
tmux set-buffer -t <session> -- <message>
tmux paste-buffer -t <session>:<window>.<pane>
tmux send-keys -t <session>:<window>.<pane> C-m
tmux capture-pane -t <session>:<window>.<pane> -p -S <lines>
```

The Codex process may hold useful conversational context, but it is not authoritative application state. The backend transcript, run metadata, uploaded document references, candidate output files, validation results, and promotion records are the durable source of truth.

Pane capture is user-facing transcript/log material only. It must not be parsed as safety-critical state.

At the end of onboarding, the backend sends a finalization instruction that asks Codex to write structured JSON files under `runs/<run_id>/output/`, starting with `user_profile.json`. Those files must then pass the normal schema validation and import path before they affect application state.

### 2. File-output worker mode

Use this mode for non-chat structured agent tasks.

The backend prepares a run folder with `task.md`, `instructions.md`, scoped `input/`, empty `output/`, and `logs/`. It invokes Codex through `codex exec` with the least permissions needed. Where a single structured final response is appropriate, use `--output-schema` and `-o`; where the agent must write multiple output files, the prompt must require writes under `output/`, and the backend must import those files after the process exits.

Stdout, stderr, JSONL events, exit code, duration, and command metadata are execution logs. They are useful for debugging, retry decisions, and dashboard observability, but not for safety-critical state.

## Operational Behavior

### Startup

For tmux chat mode, the adapter should:

- Verify the configured WSL distro is reachable.
- Verify the tmux session and pane exist, or create/attach according to configuration.
- Detect whether the pane is at a shell prompt or already running Codex.
- Launch `codex` in the configured repository when needed.
- Handle the initial repository trust prompt only for the configured local repository.

For file-output worker mode, the adapter should:

- Verify the run folder exists.
- Verify expected `input/`, `output/`, `logs/`, `task.md`, and `instructions.md` paths.
- Invoke `codex exec` with explicit working directory, sandbox, timeout, and prompt.

### Message Routing

For tmux chat mode:

- Use tmux paste buffers rather than nested shell quoting.
- Persist the user message before sending it to Codex.
- Capture the pane after Codex responds.
- Persist the captured assistant message and raw capture metadata.
- Treat reply extraction as best-effort display logic; retain raw capture for audit/debugging.

### Timeouts

Each send operation has a configurable timeout. On timeout, the backend marks the message attempt as failed or timed out and does not assume Codex completed the requested work.

Long-running finalization should have a separate, larger timeout from normal chat replies.

### Failure

Failures include:

- Missing WSL distro.
- Missing tmux executable, session, window, or pane.
- Codex process not started.
- Trust prompt not resolved.
- Command timeout.
- Pane capture failure.
- Expected output file missing.
- Schema validation failure.

Failures are recorded as backend state and audit/log entries. A failed transport attempt must not create approved profile, policy, CV, send intent, gate, reservation, outreach, or email state.

### Cancellation

Cancellation may send Ctrl-C to the tmux pane for the current turn. For stronger cancellation or reset, the backend may terminate or recreate the tmux session according to configuration. Cancellation records should be visible in the onboarding transcript/logs.

### Retry

Retries are allowed for transport failures and missing/invalid output files, but retries must be explicit backend actions. The retry prompt should include the validation error and request only a corrected output file. Previously failed outputs remain auditable.

## Safety Boundaries

Codex receives no secrets, no email credentials, no Gmail access, and no send capability.

The backend must not expose a send endpoint through this runtime. Codex must not call Gmail or any future email adapter.

The backend remains authoritative for:

- Database state.
- Dedupe.
- User policy.
- Safety gates.
- Send limits.
- Audit logs.
- Snapshot promotion.
- Future irreversible actions.

All safety-relevant Codex output must be a file under `output/`, validated against `schemas/`, imported by the backend, and reviewed or gated deterministically before use.

## Consequences

- Onboarding can provide a true conversational UI by keeping a Codex TUI session open in tmux.
- The backend still stores durable transcript/session state so the application is not dependent on Codex process memory.
- Structured tasks can still use `codex exec`, which is a better fit for repeatable file-output jobs.
- The tmux adapter needs careful state detection and failure handling because pane output is a terminal UI, not a formal protocol.
- Tests for the tmux adapter should use fake runners and captured fixture text rather than requiring a real WSL/tmux/Codex session.

## Alternatives Considered

### Use only `codex exec`

Rejected for onboarding chat. It is the documented path for non-interactive automation and remains appropriate for structured worker tasks, but it does not provide the continuous chat feel wanted for onboarding.

### Parse pane capture as authoritative output

Rejected. Terminal capture is fragile and user-facing. It can support the chat transcript, but application state must come from validated files.

### Add the OpenAI API to the backend

Rejected for this phase. The project intentionally uses the local Codex CLI runtime and does not need a backend OpenAI API dependency for this tick.

### Give Codex direct database or email access

Rejected. It violates the project boundary that agents produce files and programs make decisions.

