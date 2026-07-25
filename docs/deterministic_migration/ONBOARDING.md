# Onboarding Migration Plan

## Goal

Move directly confirmed, structurally representable onboarding facts and policy choices into application-owned state without reducing the quality or flexibility of the AI recruiter.

The recruiter remains responsible for conversation, coaching, semantic document interpretation, contradiction discovery, and career-claim proposals.

## Preserved Capabilities

The following existing behavior must remain available:

- chat-only onboarding;
- English and German recruiter interaction;
- optional CV/resume upload;
- deterministic document text extraction;
- career-history and claim discovery;
- follow-up questions and corrections;
- candidate user profile, master CV profile, policy, and review artifacts;
- repair of invalid artifacts;
- explicit review and promotion;
- immutable approved snapshots.

No structured control may become a mandatory extra onboarding step.

## Field Ledger

Add a workspace- and run-scoped onboarding field ledger with append-only events and a current projection.

Each event contains:

- backend-generated event ID;
- registered field key;
- typed value or clear operation;
- actor and source transcript entry when applicable;
- expected and resulting revision;
- source type;
- review state;
- timestamp.

Add an optional endpoint:

```text
POST /onboarding/chat/{run_id}/field-events
```

The request contains:

- `field_key`;
- `operation`: `set`, `append`, `remove`, or `clear`;
- typed `value` where required;
- `expected_revision`.

The backend generates identity, provenance, timestamps, and revision. Unsupported field keys or invalid types fail without modifying the ledger.

## Structurally Supported Fields

The first version supports:

- display name and contact details;
- work authorization;
- directly confirmed languages and levels;
- target locations and relocation;
- remote, hybrid, and onsite preferences;
- time zones and travel limits;
- availability and start date;
- explicitly selected target roles and seniority;
- employment type and minimum duration;
- company, domain, industry, keyword, and role exclusions;
- forbidden claims;
- daily and weekly outreach limits;
- dedupe preferences;
- communication tone selected from supported values.

Open-ended experience, project, education, achievement, skill, and credential claims remain agent proposals unless they come from an existing approved snapshot.

## Frontend Behavior

Keep the chat as the primary surface. Add optional structured cards when the recruiter reaches a supported topic.

- A card submits a field event.
- The transcript records a user-visible confirmation without duplicating raw sensitive values unnecessarily.
- The recruiter receives a compact ledger summary so it does not ask for an already confirmed field.
- Users may answer in prose instead; the agent path remains available.
- Corrections create new events rather than mutating history.

## Deterministic Materializer

Create a pure snapshot materializer that takes:

- confirmed field-ledger projection;
- existing approved snapshot bundle;
- agent candidate artifacts;
- run metadata and locale.

Precedence:

1. explicit field event in the current run;
2. unchanged value from the pinned approved snapshot;
3. agent candidate value with its original evidence and review state;
4. missing value plus a review item.

The backend owns:

- profile, policy, review, and snapshot IDs;
- schema versions;
- timestamps;
- cross-file references;
- direct-confirmation provenance;
- conservative policy defaults;
- deduplication of arrays;
- review-item generation for conflicts and missing required information.

The agent continues to propose the master CV claim ledger. Claims cannot become approved merely because a structurally related field was confirmed.

## Rollout

### Stage 1: capture only

Persist field events and show them in onboarding state. Continue using all current agent artifacts unchanged.

### Stage 2: shadow materialization

Materialize candidate `user_profile.json`, `policy.json`, and backend review items beside agent artifacts. Compare normalized fields, provenance, review requirements, and completeness. Do not import shadow files.

### Stage 3: deterministic-first by field family

Enable only field families with a `ready` report. Backend values override agent values for those exact fields. Uncovered fields still come from the agent candidate and retain review state.

### Stage 4: backend snapshot assembly

When all direct-field families are ready, the backend assembles user profile and policy candidates. The agent still writes:

- career claim proposals;
- contradictions;
- narrative review explanations;
- unstructured preference proposals.

Chat-only users automatically fall back to the existing artifact path where no ledger evidence exists.

## Comparison Metrics

For every replay:

- required-field completeness;
- exact match for direct confirmations;
- preservation of existing approved values;
- number and severity of review items;
- invented or unsupported personal facts;
- schema validation;
- promotion outcome;
- onboarding completion outcome;
- number of unnecessary repeated recruiter questions.

Critical mismatches:

- a direct confirmation changed or omitted;
- an unsupported fact marked approved;
- a prior approved value silently lost;
- a policy exclusion or limit weakened;
- a review blocker omitted;
- a cross-file ID mismatch;
- a chat-only run can no longer finish.

## Test Plan

- Field-event validation, optimistic concurrency, replay, and workspace isolation.
- Set, append, remove, clear, correction, and duplicate event behavior.
- English and German structured cards.
- Chat-only path with zero events.
- Uploaded-document path with agent claim proposals.
- Existing approved snapshot carry-forward.
- Direct correction overriding prior snapshot.
- Conflict between agent artifact and explicit event.
- Missing required field creating review rather than invention.
- Schema-valid deterministic materialization.
- Promotion behavior identical for equivalent artifacts.
- Automatic agent fallback on unsupported fields.
- Existing onboarding API, upload, repair, promotion, localization, and browser journeys remain green.

## Cutover Criteria

- At least 25 replayable sessions covering the roadmap categories.
- Every direct confirmation is reproduced exactly.
- Zero unsupported facts or weakened policy values.
- Required-field completeness and successful finish rate are no lower than baseline.
- Human review finds no loss in recruiter usefulness or contradiction discovery.
- Any unsupported language or field shape is routed to the agent path.
