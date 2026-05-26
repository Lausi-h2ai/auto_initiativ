# AM-006-005 Onboarding Recruiter Artifacts

## Summary

Implemented the first artifact-producing onboarding loop for the tmux-backed recruiter chat.

The onboarding start path now sends a recruiter instruction prompt once per run, without storing it as a user chat message. The prompt tells Codex to interview like a private recruiter, read local run input context, avoid invented facts, and write candidate artifacts under `runs/<run_id>/output/`.

## Changes

- Added `backend/app/agents/onboarding_recruiter_prompt.py`.
- Extended the onboarding chat adapter with `ensure_recruiter_prompt()`.
- Updated onboarding finalization to request:
  - `user_profile.json`
  - `master_cv_profile.json`
  - `policy.json`
  - `onboarding_review.json`
- Expanded onboarding import expectations so all four files are validated.
- Added onboarding artifact status/import API responses and endpoints:
  - `GET /onboarding/chat/{run_id}/artifacts`
  - `POST /onboarding/chat/{run_id}/import-artifacts`
- Added dashboard artifact visibility and a `Validate Artifacts` control on Profile and Onboarding views.
- Updated docs/backlog to reflect the recruiter prompt and candidate artifact workflow.

## Safety

- No Gmail sending was added.
- No real email adapter sending was added.
- No OpenAI API dependency was added.
- No autonomous sending was added.
- No campaign implementation was added.
- Candidate artifacts remain unapproved until backend review/promotion.
- Existing validation, promotion, gate, and audit infrastructure remains in place.

## Validation

- `uv run --python 3.12 --extra test pytest`
  - `227 passed, 1 skipped`
- Playwright checked the local dashboard:
  - Profile page loads.
  - Onboarding page loads.
  - `Validate Artifacts` controls are visible.
  - All four expected artifact filenames are visible.
  - Artifact status API reports missing artifacts clearly when files are absent.

## Follow-Up

Next ticks should keep moving toward first-class onboarding session records, profile promotion UI, campaign creation, and campaign research tmux runs. The current artifact import path is file-backed and usable, but onboarding session state is still not a first-class database record.
