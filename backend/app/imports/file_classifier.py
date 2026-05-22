from __future__ import annotations


FILENAME_TO_SCHEMA = {
    "company_candidate.json": "company_candidate.schema.json",
    "contact_candidate.json": "contact_candidate.schema.json",
    "email_draft.json": "email_draft.schema.json",
    "fit_evaluation.json": "fit_evaluation.schema.json",
    "gate_result.json": "gate_result.schema.json",
    "master_cv_profile.json": "master_cv_profile.schema.json",
    "onboarding_review.json": "onboarding_review.schema.json",
    "policy.json": "policy.schema.json",
    "send_intent.json": "send_intent.schema.json",
    "user_profile.json": "user_profile.schema.json",
}

EXPECTED_FILENAMES = tuple(FILENAME_TO_SCHEMA.keys())


def classify_filename(filename: str) -> str | None:
    """Return the exact schema filename for a known Phase 1 output filename."""
    return FILENAME_TO_SCHEMA.get(filename)
