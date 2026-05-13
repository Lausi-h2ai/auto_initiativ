# Safety Gate Specification

## Purpose

The safety gate is the deterministic backend service that decides whether a `send_intent` can progress. In the first implementation, all successful decisions still remain dry-run safe.

## Inputs

- `send_intent.json`
- Stored user profile
- Stored master CV profile
- Stored policy
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
- No required field is low-confidence or marked `needs_review`.
- Transactional reservation is available before sending.
- Audit log is written before and after evaluation.

## Gate Outcomes

Allowed statuses:

- `passed_dry_run`
- `blocked`
- `needs_review`
- `reserved`
- `sent`
- `send_failed`

The foundation should only use `passed_dry_run`, `blocked`, and `needs_review`.

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

## Transactional Reservation

Before any future send, the backend must create a reservation inside the same database transaction used for dedupe checks.

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
- A send result event after any future adapter call.

Audit records must be append-only.

## Determinism

Gate logic must be pure with respect to the same database snapshot and input file. No LLM calls, web calls, or prompt interpretation are allowed inside the gate.

