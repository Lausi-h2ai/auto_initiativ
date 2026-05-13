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

## Review Output

Onboarding output should make review easy by grouping:

- Verified facts
- User-claimed facts
- Inferred items
- Contradictions
- Missing required information
- Policy decisions

