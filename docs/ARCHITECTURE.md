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

### Codex Runtime

Codex works from prepared run folders:

```text
runs/<run_id>/
  input/
  output/
  logs/
  task.md
  instructions.md
```

The backend prepares input files and instructions. Codex reads from `input/` and writes only to `output/`. The backend imports and validates outputs.

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

Real-recipient Gmail delivery is a separate opt-in:

```text
EMAIL_SENDING_ENABLED=true
EMAIL_PROVIDER=gmail
EMAIL_ALLOW_REAL_RECIPIENTS=true
```
