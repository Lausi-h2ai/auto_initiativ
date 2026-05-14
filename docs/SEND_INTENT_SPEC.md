# Send Intent Specification

## Purpose

`send_intent.json` is the agent-produced file that asks the backend to consider an outreach email for sending.

It is not permission to send.

## Authority

Only the backend safety gate can decide whether a send intent passes. In dry-run mode, passing means the intent is eligible for review, not that an email is sent.

The gate can run in `evaluate_only` mode or future `reserve_for_send` mode. A send intent itself must not request or imply adapter execution.

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
- Immutable policy snapshot ID
- Immutable user profile snapshot ID
- Immutable master CV profile snapshot ID
- Confidence
- Review flags

Snapshot IDs must refer to immutable records. If the user profile, policy, or master CV changes later, the backend must create a new snapshot and future send intents must reference that new snapshot.

## Claim Ledger Rule

Every CV bullet and every user-descriptive email claim must reference approved claim IDs from the immutable `master_cv_profile.json` snapshot.

Examples of user-descriptive claims:

- Work experience
- Skills
- Education
- Projects
- Achievements
- Languages
- Availability or work authorization, when presented as a factual claim

Unsupported claims must be removed or marked for review. A send intent with unreferenced user-descriptive claims must fail the gate.

## Contact Safety

Send intents should prefer publicly listed professional contacts.

Private or personal email addresses must be marked for review or blocked according to policy. Guessed, pattern-inferred, or weakly sourced emails must never be treated as ready to send without backend review.

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
3. Resolve immutable profile, policy, and master CV snapshots.
4. Resolve referenced records.
5. Validate claim IDs and attachments.
6. Run the safety gate in `evaluate_only` mode by default.
7. Store the gate result.
8. Display the result in the dashboard.

## Dry-Run First

The first implementation must never call an email adapter. Gate-passing send intents should be visible in the UI as `passed_evaluate_only`.
