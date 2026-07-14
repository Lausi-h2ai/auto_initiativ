from __future__ import annotations

import json
from datetime import timedelta

import pytest

from backend.app.agents.job_verification_runtime import JobVerificationRuntime
from backend.app.core.config import get_settings
from backend.app.db.models import JobPosting, utc_now
from backend.app.imports.job_normalizer import JobNormalizationService


def _job(*, valid_through=None) -> JobPosting:
    return JobPosting(
        job_id="job-verification-rule",
        external_company_id="company-verification-rule",
        title="Verified role",
        source_url="https://employer.example/role",
        canonical_url="https://employer-ats.example/role",
        application_url="https://employer-ats.example/role/apply",
        source_domain="employer-ats.example",
        source_kind="ats",
        fingerprint="job-verification-rule",
        valid_through=valid_through,
    )


def test_future_deadline_and_employer_matched_ats_can_verify_without_posting_date(db_session):
    job = _job(valid_through=utc_now() + timedelta(days=14))
    flags: list[str] = []

    status = JobNormalizationService(db_session)._verification_status(
        job,
        {
            "page_accessible": True,
            "apply_route_available": True,
            "closed_signal_found": False,
            "employer_identity_match": True,
            "http_status": 200,
        },
        flags,
    )

    assert status == "verified_open"
    assert flags == ["missing_date_posted"]


def test_missing_posting_date_and_deadline_still_requires_review(db_session):
    job = _job()
    flags: list[str] = []

    status = JobNormalizationService(db_session)._verification_status(
        job,
        {
            "page_accessible": True,
            "apply_route_available": True,
            "closed_signal_found": False,
            "employer_identity_match": True,
            "http_status": 200,
        },
        flags,
    )

    assert status == "needs_review"
    assert flags == ["missing_date_posted"]


def test_vacancy_verifier_contract_fails_on_any_non_target_output(tmp_path, monkeypatch):
    root = tmp_path / "verification-run"
    for folder in ("input", "output/jobs", "output/job_fit_evaluations"):
        (root / folder).mkdir(parents=True, exist_ok=True)
    (root / "input" / "target_job.json").write_text(
        json.dumps({"job_id": "selected-job"}), encoding="utf-8"
    )
    (root / "output" / "jobs" / "selected.json").write_text(
        json.dumps({"job_id": "selected-job"}), encoding="utf-8"
    )
    (root / "output" / "job_fit_evaluations" / "selected.json").write_text(
        json.dumps({"job_id": "selected-job"}), encoding="utf-8"
    )
    runtime = JobVerificationRuntime(settings=get_settings())
    monkeypatch.setattr(runtime, "_run_root", lambda _run_id: root)

    runtime._validate_verification_outputs("verification-run")

    (root / "output" / "jobs" / "unexpected.json").write_text(
        json.dumps({"job_id": "unexpected-job"}), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="exactly the selected job"):
        runtime._validate_verification_outputs("verification-run")
