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

COMPANY_RESEARCH_DIRECTORY_TO_SCHEMA = {
    "companies": "company_candidate.schema.json",
    "contacts": "contact_candidate.schema.json",
    "fit_evaluations": "fit_evaluation.schema.json",
}


def classify_filename(filename: str) -> str | None:
    """Return the exact schema filename for a known Phase 1 output filename."""
    return FILENAME_TO_SCHEMA.get(filename)


def classify_output_path(path: str) -> str | None:
    """Return a schema filename for a run output relative path."""
    normalized = path.replace("\\", "/").strip("/")
    if "/" not in normalized:
        return classify_filename(normalized)
    parent, filename = normalized.rsplit("/", 1)
    if not filename.endswith(".json"):
        return None
    directory = parent.rsplit("/", 1)[-1]
    return COMPANY_RESEARCH_DIRECTORY_TO_SCHEMA.get(directory)
