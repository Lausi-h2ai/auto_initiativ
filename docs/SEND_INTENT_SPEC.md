# Send Intent Specification

## Purpose

`send_intent.json` is the agent-produced file that asks the backend to consider an outreach email for sending.

It is not permission to send.

## Authority

Only the backend safety gate can decide whether a send intent passes. In dry-run mode, passing means the intent is eligible for review, not that an email is sent.

## Required Content

A send intent must include:

- Intent ID
- Run ID
- Company ID
- Contact ID
- Email draft ID
- Recipient email
- Subject
- Body
- Attachments
- Source references
- Policy snapshot ID
- Profile snapshot ID
- Master CV profile snapshot ID
- Confidence
- Review flags

## Forbidden Content

A send intent must not include:

- Credentials
- Gmail API calls
- Instructions to bypass gates
- Unsupported CV claims
- Personalization with no source reference
- Low-confidence required fields marked as ready

## Import Behavior

The backend should:

1. Validate the schema.
2. Normalize recipient and company domain.
3. Resolve referenced records.
4. Validate attachments.
5. Run the safety gate.
6. Store the gate result.
7. Display the result in the dashboard.

## Dry-Run First

The first implementation must never call an email adapter. Gate-passing send intents should be visible in the UI as `passed_dry_run`.

