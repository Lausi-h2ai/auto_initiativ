# Data Model

This document describes the target persistent entities. Exact table names can change during implementation, but the relationships and constraints should remain.

## Core Entities

### UserProfileSnapshot

Stores imported `user_profile.json` versions. Snapshots allow future sends to reference the profile version used at drafting time.

### MasterCvProfileSnapshot

Stores approved career claims and provenance. CV tailoring must only use claims from this entity.

### PolicySnapshot

Stores user-specific outreach policy, exclusions, blocked domains, contact rules, review thresholds, and send limits.

### Run

Represents a Codex run folder with:

- Run ID
- Agent type
- Input paths
- Output paths
- Status
- Started and completed timestamps
- Validation results

### Company

Represents a researched company. Dedupe should include normalized domain and policy-specific company keys.

### Contact

Represents a possible recipient. Dedupe must include normalized recipient email.

### FitEvaluation

Stores agent fit analysis, score, reasons, risks, and policy flags.

### EmailDraft

Stores draft subject and body with source-backed personalization references.

### SendIntent

Stores the exact structured request that an agent wants the backend to consider for sending.

### GateResult

Stores deterministic gate decision, performed checks, blocking reasons, and reservation references.

### SendReservation

Prevents duplicate or racing sends. Must be created transactionally before any future adapter call.

### SentMessage

Stores future send results from an email adapter. This does not exist in the foundation as executable sending code.

### AuditLog

Append-only log of imports, validations, gate decisions, reservations, and future sends.

## Required Constraints

- Unique normalized recipient email for contacted recipients where policy forbids repeat contact.
- Unique normalized company key for contacted companies where policy forbids repeat company outreach.
- Unique active send reservation per recipient email.
- Unique active send reservation per company key when company-level dedupe applies.
- Foreign keys from send intents to company, contact, draft, profile snapshot, policy snapshot, and attachments.

## Normalization

Normalize before dedupe:

- Email addresses lowercase and trimmed.
- Domains lowercase, punycode-normalized where needed, and stripped of `www.`.
- Company names trimmed, case-folded, and optionally mapped to canonical company IDs.

## Audit Requirements

Audit logs should include:

- Actor type: `backend`, `codex_agent`, or `user`.
- Action.
- Entity type and ID.
- Input file path or API request ID.
- Result status.
- Machine-readable reason codes.
- Timestamp.

