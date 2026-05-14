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
- Explaining blocks and review requirements.
- Preflight checks before a user approves anything.

This mode must never create a send reservation and must never call an email adapter.

### `reserve_for_send`

Runs the same checks as `evaluate_only`, then attempts a transactional send reservation if all checks pass.

Use this mode only after future implementation adds explicit user approval or an autonomous sending policy. A successful reservation means the backend may proceed to a future email adapter. It does not mean the email was sent.

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
- No required field is low-confidence or marked `needs_review`.
- Contact email safety rules pass.
- In `reserve_for_send` mode, transactional reservation is available before adapter handoff.
- Audit log is written before and after evaluation.

## Contact Safety

The gate should prefer publicly listed professional contact addresses.

Block or require review for:

- Private or personal email addresses.
- Guessed or pattern-inferred emails.
- Emails found only in weak, stale, scraped, or unverifiable sources.
- Contacts whose professional relationship to the company is unclear.

The policy may decide whether these cases are hard blocks or review requirements, but missing policy should default to `needs_review` or `blocked`.

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
- Any required field needs review.
- The email body contains claims not traceable to approved profile claims or sources.
- Any CV bullet or user-descriptive email claim lacks an approved claim ID.
- The recipient is private, personal, guessed, or weakly sourced and policy requires blocking.

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

This implementation does not create send reservations, call an email adapter, call Gmail, send email, or use OpenAI. The next tick, `AM-003-003`, should expand the test matrix so each required blocking reason has focused coverage.
