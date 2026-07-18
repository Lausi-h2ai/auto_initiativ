# Onboarding Data Contract Plan

Status: `planned`
Tick: `AM-005-001`
Date: 2026-05-15

## Objective

Define the Phase 5 onboarding data contract before implementation. The contract must let agents collect user context while keeping the backend in charge of validation, review, promotion, immutable snapshots, and future safety gates.

This is a planning tick only. It adds no Gmail integration, email adapter, send behavior, OpenAI dependency, reservation mode, or autonomous irreversible action.

## Current Baseline

Existing validated snapshot outputs:

- `user_profile.json`: identity, preferences, work authorization, languages, provenance summary, and review items.
- `master_cv_profile.json`: claim ledger with stable `claim_id`, provenance, and `approved_for_tailoring`.
- `policy.json`: exclusions, outreach dedupe policy, send limits, review thresholds, and forbidden claims.

Existing provenance shape is consistent across these files:

- `source_type`: `verified_document`, `user_claim`, `inferred`, or `needs_review`.
- `confidence`: numeric 0 to 1.
- `needs_review`: boolean.
- `source_refs`: stable references to source documents or interview notes.

Existing persistence stores immutable raw JSON snapshots for user profile, master CV, and policy records with content hashes and a coarse `status`.

Known gaps to close during implementation:

- Snapshot promotion is currently represented only by a free-form status string; there is no dedicated active snapshot pointer or promotion event model.
- Current unique external IDs (`profile_id` and `policy_id`) mean versioning needs either new IDs per approved snapshot or a later schema change.
- `approved_for_tailoring` is not schema-bound to provenance, so backend validation must reject approved claims whose provenance still needs review.
- Claim IDs are required but not schema-enforced as unique within one `master_cv_profile.json`.
- `review_items` are currently too small for full onboarding review; `onboarding_review.json` should carry the richer lifecycle.

## Contract Principles

1. The onboarding agent produces reviewable candidates, not approved truth.
2. Every factual claim must carry provenance and source references.
3. Every useful but uncertain, inferred, contradictory, or policy-relevant item must be reviewable.
4. The backend promotes approved candidates into immutable snapshots.
5. Historical snapshot meaning must not change. Corrections create new snapshot IDs.
6. Future CV tailoring and user-descriptive email claims may use only approved master CV claim IDs.
7. Policy exclusions are learned from the user and stored in `policy.json`; they are not hardcoded globally.

## Onboarding Inputs

An onboarding run should receive an input bundle with these logical sections:

- `run_context`: run ID, created timestamp, operator, and source directory.
- `source_documents`: stable source refs, file paths, document type, optional content hash, and trust level.
- `interview_notes`: stable note refs, timestamps, prompt/answer text or summary, and whether the user directly confirmed the content.
- `existing_snapshots`: optional current profile, master CV, and policy snapshot IDs for comparison.
- `review_policy`: confidence thresholds and which source classes require manual review before promotion.

Implementation can start with file manifests and interview-note JSON in the run folder. Do not require a database migration until the review workflow needs durable draft state.

## Onboarding Outputs

The onboarding run should write a review bundle plus candidate snapshot files:

- `onboarding_review.json`: review index for all candidate facts, contradictions, inferred items, policy decisions, and missing required information.
- `user_profile.json`: candidate user profile snapshot.
- `master_cv_profile.json`: candidate claim ledger snapshot.
- `policy.json`: candidate policy snapshot, including learned exclusions.

The existing three snapshot files remain the import boundary for promoted data, but Phase 5 should treat them as candidates until backend review/promotion approves them.

## Review States

Use deterministic review states at the item level:

- `proposed`: generated from onboarding evidence and waiting for review.
- `approved`: accepted for promotion.
- `rejected`: explicitly excluded from promotion.
- `needs_clarification`: insufficient or contradictory evidence.
- `superseded`: replaced by a newer reviewed item.

Snapshot-level statuses should be:

- `candidate`: imported or staged but not usable for automated tailoring/outreach.
- `approved`: promoted and usable according to its contract.
- `superseded`: replaced by a newer approved snapshot.
- `rejected`: not usable.

The existing snapshot table `status` fields can support this lifecycle without an immediate migration, but implementation should centralize allowed status values and transitions.

## Promotion Rules

Backend promotion must validate all candidate files against schemas and then apply these deterministic checks:

- Required fields are present and schema-valid.
- Every factual item has `source_type`, `confidence`, `needs_review`, and `source_refs`.
- `needs_review: true` items cannot be promoted as approved facts.
- `source_type: needs_review` items cannot be promoted as approved facts.
- `inferred` items require explicit user approval before promotion.
- Contradictions must be resolved or carried as rejected/needs-clarification review items.
- `master_cv_profile.json` claims are usable for tailoring only when `approved_for_tailoring: true` and provenance is approved.
- Claim IDs must be unique within a promoted `master_cv_profile.json`.
- `policy.json` exclusions must come from user-approved policy decisions or verified documents, with source refs.
- New approved snapshots receive new stable snapshot IDs when content changes.
- Previous approved snapshots are marked `superseded`, not mutated.

## File-Specific Rules

### `user_profile.json`

Use for user identity, preferences, work authorization, languages, availability, and communication tone.

Promotion requirements:

- Required identity and preferences must be approved or explicitly left absent when optional.
- Low-confidence preferences remain review items.
- Work authorization and availability are policy-relevant and require direct user confirmation or verified-document provenance before approved promotion.
- The final profile-approval checkbox is one explicit user-confirmation action for every remaining profile-level `needs_review` item shown in the prepared review. The backend records that confirmation in provenance and audit history atomically; users do not need to approve those fields one by one.

### `master_cv_profile.json`

Use as the only claim ledger for future CV tailoring and user-descriptive outreach claims.

Promotion requirements:

- Every claim has a stable `claim_id`.
- Claims with `needs_review: true` or unresolved contradictions must set `approved_for_tailoring: false`.
- Inferred claims stay unapproved until user-confirmed.
- Corrections create a new claim ID or a new snapshot that preserves historical meaning.

### `policy.json`

Use for learned exclusions, dedupe preferences, limits, review thresholds, and forbidden claims.

Promotion requirements:

- Exclusions are learned during onboarding and stored with provenance.
- Exclusions that are uncertain or inferred require review before promotion.
- Send limits and manual-review policy require explicit user confirmation.
- Missing policy defaults must remain conservative in backend gates.

## Recommended Implementation Ticks

### AM-005-002: Onboarding Review Workflow

Implement staging and promotion for candidate `user_profile.json`, `master_cv_profile.json`, and `policy.json`.

Acceptance:

- Candidate snapshots import as `candidate`.
- Backend exposes deterministic review/promotion actions without sending.
- Approved snapshots become usable by later runs; unapproved claims cannot be used automatically.
- Promotion writes audit logs and supersedes previous approved snapshots without mutating old content.
- Promotion rejects approved master CV claims with review-needed provenance and duplicate claim IDs.
- Policy promotion requires approved exclusion provenance, explicit confirmation for send limits and manual-review policy, and conservative handling of missing defaults.

### AM-005-003: Onboarding Review Schemas

Add `onboarding_review.schema.json` and matching Pydantic model.

Acceptance:

- Review items include stable IDs, target file, target JSON pointer, proposed value, provenance, confidence, state, reviewer metadata, and resolution notes.
- Contradictions and missing required information are first-class review item types.
- Schema validation rejects hidden side effects and unknown fields.

### AM-005-004: Onboarding Input Bundle

Define and validate an onboarding input manifest for source documents and interview notes.

Acceptance:

- Source refs are stable and can be linked from all output provenance.
- Document trust level and user-confirmed interview notes are represented.
- The backend can reject candidate outputs that cite unknown source refs.

## Open Questions

- Whether review actions should be API-only first or also exposed in the dashboard during Phase 5.
- Whether candidate review state should initially live only in raw JSON and audit logs or receive dedicated normalized tables.
- Whether profile, master CV, and policy snapshot IDs should be generated by agents or reserved by the backend during promotion.
