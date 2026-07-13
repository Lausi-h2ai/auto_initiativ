# Onboarding Specification

## Purpose

Onboarding creates the durable user context required for safe outreach:

- `user_profile.json`
- `master_cv_profile.json`
- `policy.json`
- Optional CV templates

## Interview Topics

The onboarding agent should ask about:

- Work experience
- Projects
- Education
- Skills
- Values
- Preferences
- Target roles
- Target locations
- Language preferences
- Relocation preferences
- Remote and hybrid preferences
- Exclusion criteria
- Communication tone
- Work authorization constraints
- Availability and start date

It may ask the user to provide old CVs, cover letters, LinkedIn text, portfolios, or other career documents.

## Dashboard Chat Flow

The onboarding dashboard presents a chat window backed by a resumable Pi RPC session in a run-specific workspace.

The backend should:

- Start or resume the run-specific Pi RPC session using the onboarding workload policy.
- Send user messages as Pi RPC prompts and consume structured response events.
- Require a non-empty recruiter greeting before startup succeeds, and append clean assistant replies to the onboarding transcript.
- Persist the transcript as audit/review context, not as validated profile state.
- Keep uploaded documents under the run `input/` folder and expose them only through the restricted onboarding extension.

At the end of the chat, the backend should send a finalization instruction asking Codex to write:

- `runs/<run_id>/output/user_profile.json`

The file must match `schemas/user_profile.schema.json`. It must include provenance, confidence, source references, and review flags as required by the schema. If Codex lacks evidence for a field, it must either omit the optional field or mark the relevant item as `needs_review`.

The backend must validate and import the JSON file through the normal import pipeline. The imported profile remains a candidate snapshot until the review/promotion workflow approves it.

## Provenance Classes

Every factual claim should be classified as one of:

- `verified_document`: found in an uploaded document or trusted source.
- `user_claim`: stated by the user during onboarding.
- `inferred`: inferred by the agent and not directly stated.
- `needs_review`: uncertain, contradictory, or requiring user confirmation.

## Exclusion Criteria

Exclusions such as defense, gambling, surveillance, oil and gas, crypto, or any other category must not be hardcoded globally.

They must be learned during onboarding, stored in `policy.json`, and applied deterministically by the backend.

## Master CV Rules

Future CV tailoring may only use claims from `master_cv_profile.json`.

The master CV profile is also the claim ledger for outreach. Every approved claim needs a stable claim ID. Every future CV bullet and every user-descriptive email claim must reference one or more approved claim IDs.

The agent must not invent:

- Employers
- Dates
- Titles
- Degrees
- Certifications
- Skills
- Achievements
- Metrics
- Languages

If a claim is useful but uncertain, it must be marked `needs_review` and excluded from automatic tailoring until approved.

Approved claims should remain immutable within a snapshot. Corrections should create a new master CV profile snapshot instead of changing the historical meaning of old claim IDs.

## Review Output

Onboarding output should make review easy by grouping:

- Verified facts
- User-claimed facts
- Inferred items
- Contradictions
- Missing required information
- Policy decisions
