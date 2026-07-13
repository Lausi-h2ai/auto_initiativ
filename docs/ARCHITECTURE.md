# Architecture

## Central Design Decision

Codex agents are file-producing workers. They do not own application state and they cannot send email.

The backend imports structured files, validates them, persists normalized data, runs deterministic safety gates, and eventually calls email adapters.

## Components

### Frontend

Target frontend views:

- Dashboard
- Runs
- Companies
- Contacts
- Applications
- Send queue
- Sent emails
- Blocked intents
- Audit logs
- Settings

The UI should expose backend state, not agent assumptions.

### Backend

Target backend stack:

- FastAPI for HTTP APIs.
- Postgres for durable state.
- SQLModel or SQLAlchemy for database models.
- Pydantic for import and API validation.
- Deterministic send gate service.
- Email adapter interface with a future Gmail implementation.

The backend has no dependency on an LLM for safety decisions.

### Agent Runtime

All application-owned agent work runs through Pi RPC from prepared run folders:

```text
runs/<run_id>/
  input/
  output/
  logs/
  task.md
  instructions.md
```

The backend starts Pi in RPC mode with built-in tools and automatic resource discovery disabled. Each workload receives one explicit, narrowly scoped extension. Agents read approved inputs and write only candidate outputs; the backend imports and validates those outputs.

The WSL tmux bridge and direct `codex exec` adapter remain available only for developer diagnostics and legacy tests. They are not wired into onboarding, research, drafting, or another application workflow.

### Agent Model Policy

Default models for agent workloads are centralized in `backend/app/core/agent_models.py`:

- Onboarding uses `gpt-5.6-sol` for the flagship recruiting conversation.
- Company research uses `gpt-5.6-terra` for read-heavy discovery.
- Application drafting uses `gpt-5.6-luna` for efficient document generation.

Every application agent model default must be declared in that policy, use the GPT-5.6 family, and run through Pi RPC with the `openai-codex` provider. Tests enforce these requirements so a future runtime cannot silently introduce an older model or a second agent harness. Environment variables remain explicit operational overrides.

### Database

Postgres is the source of truth for:

- User profile snapshots
- Master CV profile claims
- Policies
- Companies
- Contacts
- Fit evaluations
- Drafts
- Send intents
- Gate results
- Send reservations
- Sent messages
- Audit logs

Dedupe must be enforced with database constraints, not only with prompts.

Profile, policy, and master CV records used by send intents must be immutable snapshots. If a profile, policy, or claim ledger changes, future work should reference a new snapshot instead of mutating history.

Every CV bullet and user-descriptive email claim must reference approved claim IDs from the relevant master CV snapshot.

Phase 1 should persist only minimal run, import, validation, and audit records. Full normalized persistence for companies, contacts, evaluations, drafts, send intents, gate results, and reservations belongs to Phase 2 and later.

## Data Flow

1. Backend creates a run folder with task instructions and input context.
2. Codex agent writes structured JSON outputs into `output/`.
3. Backend import job validates JSON schemas.
4. Backend normalizes accepted records into Postgres.
5. Backend computes gate results for any `send_intent` in `evaluate_only` mode by default.
6. Dashboard displays imported records, blocks, warnings, and audit history.
7. In disabled mode, no email adapter is called.
8. In Gmail sandbox mode, the backend sends through Gmail only after explicit dashboard approval, a frozen approval snapshot, `reserve_for_send`, and a transactional reservation. The provider recipient is rewritten to the configured sandbox recipient.
9. In real-recipient Gmail mode, the same gate and reservation path is required, plus explicit `EMAIL_ALLOW_REAL_RECIPIENTS=true`.

## Trust Boundaries

Untrusted or semi-trusted:

- Codex outputs
- Web research text
- Inferred information
- Uploaded documents until parsed and reviewed

Trusted only after deterministic validation:

- Schema-valid imported records
- Database constraints
- Backend policy checks
- Attachment existence checks
- Audit log entries

## Failure Defaults

The system defaults to blocking, review, or dry-run when information is missing, low-confidence, contradictory, unsupported, or policy-relevant.

## Email Delivery Configuration

Default behavior is non-sending:

```text
EMAIL_SENDING_ENABLED=false
EMAIL_PROVIDER=gmail_sandbox
EMAIL_ALLOW_REAL_RECIPIENTS=false
```

Sandbox Gmail delivery for live provider testing:

```text
EMAIL_SENDING_ENABLED=true
EMAIL_PROVIDER=gmail_sandbox
GMAIL_SANDBOX_RECIPIENT=laurent.hug@gmx.de
GMAIL_OAUTH_CLIENT_SECRETS_PATH=...
GMAIL_OAUTH_TOKEN_PATH=...
GMAIL_USER_ID=me
```

When `AUTH_REQUIRED=false`, these two Gmail OAuth files are treated as the local machine's sender connection even when `DEV_AUTH_BYPASS_EMAIL` supplies a workspace identity. This compatibility path is local-development only. When authentication is enabled, Gmail credentials must be stored per user through `GmailConnection`; the backend must never share the machine-local token across authenticated workspaces.

Real-recipient Gmail delivery is a separate opt-in:

```text
EMAIL_SENDING_ENABLED=true
EMAIL_PROVIDER=gmail
EMAIL_ALLOW_REAL_RECIPIENTS=true
```
