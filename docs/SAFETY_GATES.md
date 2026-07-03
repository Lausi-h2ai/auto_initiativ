# Safety Gate Specification

## Purpose

The safety gate is the deterministic backend service that decides whether a `send_intent` can progress. In the first implementation, gate evaluation is dry-run safe and must not call an email adapter.

## Gate Modes

The gate has two modes.

### `evaluate_only`

Evaluates the intent and returns a deterministic decision without reserving or sending anything.

Use this mode for:

- Dry-run Phase 1 and Phase 3 behavior.
- Dashboard preview.
- Explaining blocks and agent-remediation requirements.
- Preflight checks before backend-controlled reservation or delivery.

This mode must never create a send reservation and must never call an email adapter.

### `reserve_for_send`

Runs the same checks as `evaluate_only`, then attempts a transactional send reservation if all checks pass.

Use this mode only after future implementation adds an autonomous sending policy. A successful reservation means the backend may proceed to a future email adapter. It does not mean the email was sent.

## Inputs

- `send_intent.json`
- Immutable user profile snapshot referenced by the send intent
- Immutable master CV profile snapshot referenced by the send intent
- Immutable policy snapshot referenced by the send intent
- Company and contact records
- Attachment records
- Prior outreach records
- Send limit counters
- Audit log writer

## Required Checks

The gate must check at least:

- `send_intent` schema validity.
- Recipient email has not been previously contacted.
- Company has not been previously contacted according to configured policy.
- Domain is not blocked.
- User policy is not violated.
- Required source references exist.
- Required attachments exist.
- Daily and weekly send limits are not exceeded.
- No forbidden claims are present.
- Every CV bullet and user-descriptive email claim references approved claim IDs from the immutable master CV profile snapshot.
- No required field is low-confidence or marked with a blocking review flag.
- Contact email safety rules pass.
- In `reserve_for_send` mode, transactional reservation is available before adapter handoff.
- Audit log is written before and after evaluation.

## Contact Safety

The gate should prefer publicly listed professional contact addresses.

Block or route to agent remediation for:

- Private or personal email addresses.
- Guessed or pattern-inferred emails.
- Emails found only in weak, stale, scraped, or unverifiable sources.
- Contacts whose professional relationship to the company is unclear.

The policy may decide whether these cases are hard blocks or remediation requirements. Missing or unknown email-source policy should not block by itself, but it should not be treated as ready when confidence is low.

Generic professional recipients such as careers, jobs, recruiting, talent, HR, info, or contact addresses are allowed when they are valid emails and the draft stays appropriately general.

Unknown remote policy is descriptive uncertainty, not a blocker. Only evidence of an actual location, relocation, travel, onsite, or work-mode conflict should block or require remediation.

## Gate Outcomes

Allowed statuses:

- `passed_evaluate_only`
- `blocked`
- `needs_review`
- `reserved_for_send`

The foundation should only use `passed_evaluate_only`, `blocked`, and `needs_review`.

`sent` and `send_failed` are not gate statuses. They belong to future email adapter or send result records after a reserved intent is handed to an adapter.

## Blocking Defaults

Block when:

- Schema validation fails.
- Required records are missing.
- Sources cannot be resolved.
- Attachments cannot be found.
- Policy cannot be loaded.
- The contact or company is a duplicate under policy.
- Confidence is below configured threshold.
- Any required field has a blocking review flag.
- The email body contains claims not traceable to approved profile claims or sources.
- Any CV bullet or user-descriptive email claim lacks an approved claim ID.
- The recipient is private, personal, guessed, weakly sourced, or low-confidence and policy requires blocking.

The following review flags are informational and must not block by themselves: `generic_recipient`, `generic_contact`, `generic_contact_email`, `generic_email_recipient`, `remote_policy_unknown`, `remote_policy_unverified`, `claim_ids_present`, `claim_id_reference`, and `claim_id_references`.

## Transactional Reservation

Before any future adapter call, the backend must create a reservation inside the same database transaction used for dedupe checks. This happens only in `reserve_for_send` mode.

Reservation must include:

- `send_intent_id`
- `recipient_email`
- `company_id`
- `company_domain`
- `policy_snapshot_id`
- `created_at`
- `status`

If a unique constraint fails, the gate blocks the send.

## Audit Logging

The gate must write:

- A pre-evaluation audit event with input IDs and policy snapshot.
- A post-evaluation audit event with status, reasons, and checks performed.
- A reservation event before any future adapter call.

Future email adapter code must write separate send result events such as `sent` or `send_failed`.

Audit records must be append-only.

## Determinism

Gate logic must be pure with respect to the same database snapshot and input file. No LLM calls, web calls, or prompt interpretation are allowed inside the gate.

## Implementation Status

`AM-003-002` implemented the first deterministic `evaluate_only` gate service. It can return `passed_evaluate_only`, `blocked`, or `needs_review`, persists a gate-result record, and writes pre/post audit events.

`AM-003-003` expanded the deterministic gate test matrix across allow, block, needs-review, and warning outcomes.

`AM-007-002` added a private `ReserveForSendGateService` that runs deterministic checks and creates a transactional `SendReservation` before any private fake adapter handoff is possible.

`AM-008-001` exposed controlled backend send batches through `/send-batches` and the dashboard send queue. A send batch freezes a reviewer approval snapshot, reruns the deterministic gate in `reserve_for_send` mode, creates a transactional reservation, and only then calls the configured provider adapter.

Sending remains disabled by default. Gmail delivery requires `EMAIL_SENDING_ENABLED=true`. The default provider is `gmail_sandbox`, which rewrites the actual Gmail recipient to `GMAIL_SANDBOX_RECIPIENT` while preserving the original company recipient in the subject/body and auditable approval snapshot. Real-recipient Gmail delivery requires both `EMAIL_PROVIDER=gmail` and `EMAIL_ALLOW_REAL_RECIPIENTS=true`.

The gate itself still never calls Gmail, sends email, uses OpenAI, or interprets prompts.
