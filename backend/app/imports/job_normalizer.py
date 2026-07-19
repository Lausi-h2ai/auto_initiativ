from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from backend.app.db.models import Company, ImportedFile, JobFitEvaluation, JobPosting, JobSourceTrust, utc_now


def _json(value: str | None, fallback: Any) -> Any:
    try:
        return json.loads(value or "")
    except (json.JSONDecodeError, TypeError):
        return fallback


def _date(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def _dump(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class JobNormalizationResult:
    counts: dict[str, int]
    reason_codes: list[str]


class JobNormalizationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def normalize_run(self, run_id: str) -> JobNormalizationResult:
        files = self.session.exec(select(ImportedFile).where(ImportedFile.run_id == run_id, ImportedFile.status == "schema_validation_passed")).all()
        job_files = [item for item in files if item.schema_name == "job_posting_candidate.schema.json"]
        fit_files = [item for item in files if item.schema_name == "job_fit_evaluation.schema.json"]
        jobs: dict[str, JobPosting] = {}
        counts = {"job_postings": 0, "job_fit_evaluations": 0}
        unresolved = False
        for imported in job_files:
            data = _json(imported.raw_json, {})
            company = self.session.exec(select(Company).where(Company.company_id == data.get("company_id"))).first()
            if company is None:
                unresolved = True
            fingerprint = hashlib.sha256("|".join([str(data.get("company_id", "")), str(data.get("title", "")).casefold(), "|".join(data.get("locations") or [])]).encode()).hexdigest()
            existing = self.session.exec(select(JobPosting).where(JobPosting.job_id == data["job_id"])).first()
            job = existing or JobPosting(job_id=data["job_id"], external_company_id=data["company_id"], title=data["title"], source_url=data["source_url"], canonical_url=data["canonical_url"], application_url=data["application_url"], source_domain=data["source_domain"].lower().removeprefix("www."), source_kind=data["source_kind"], fingerprint=fingerprint)
            job.company_id = company.id if company else None
            job.external_company_id = data["company_id"]
            job.title = data["title"]
            job.source_url = data["source_url"]
            job.canonical_url = data["canonical_url"]
            job.application_url = data["application_url"]
            job.employer_website_url = data.get("employer_website_url")
            job.source_domain = data["source_domain"].lower().removeprefix("www.")
            job.source_kind = data["source_kind"]
            job.external_listing_id = data.get("external_listing_id")
            job.fingerprint = fingerprint
            job.description = data.get("description")
            job.locations_json = _dump(data.get("locations") or [])
            job.remote_policy = data.get("remote_policy")
            job.work_mode = data.get("work_mode") or "unknown"
            job.remote_regions_json = _dump(data.get("remote_regions") or [])
            duration = data.get("duration") if isinstance(data.get("duration"), dict) else {}
            job.duration_min_weeks = duration.get("minimum_weeks")
            job.duration_max_weeks = duration.get("maximum_weeks")
            job.employment_types_json = _dump(data.get("employment_types") or [])
            job.compensation_json = _dump(data.get("compensation") or {})
            job.languages_json = _dump(data.get("languages") or [])
            job.requirements_json = _dump(data.get("requirements") or [])
            job.responsibilities_json = _dump(data.get("responsibilities") or [])
            job.date_posted = _date(data.get("date_posted"))
            job.valid_through = _date(data.get("valid_through"))
            job.last_seen_at = utc_now()
            job.last_verified_at = _date(data.get("observed_at"))
            job.verification_evidence_json = _dump(data["verification_evidence"])
            job.source_refs_json = _dump(data["source_refs"])
            job.confidence = data["confidence"]
            flags = list(data["review_flags"])
            job.vacancy_status = self._verification_status(job, data["verification_evidence"], flags)
            job.review_flags_json = _dump(sorted(set(flags)))
            job.raw_json = imported.raw_json or _dump(data)
            job.imported_file_id = imported.id
            job.updated_at = utc_now()
            self.session.add(job)
            self.session.flush()
            jobs[job.job_id] = job
            counts["job_postings"] += 1
        for imported in fit_files:
            data = _json(imported.raw_json, {})
            if self.session.exec(select(JobFitEvaluation).where(JobFitEvaluation.evaluation_id == data["evaluation_id"])).first():
                continue
            job = jobs.get(data["job_id"]) or self.session.exec(select(JobPosting).where(JobPosting.job_id == data["job_id"])).first()
            if job is None:
                unresolved = True
            self.session.add(JobFitEvaluation(evaluation_id=data["evaluation_id"], job_posting_id=job.id if job else None, external_job_id=data["job_id"], company_fit_score=data["company_fit_score"], role_fit_score=data["role_fit_score"], decision=data["decision"], reasons_json=_dump(data["reasons"]), gaps_json=_dump(data["gaps"]), source_refs_json=_dump(data["source_refs"]), confidence=data["confidence"], review_flags_json=_dump(data["review_flags"]), raw_json=imported.raw_json or _dump(data), imported_file_id=imported.id))
            counts["job_fit_evaluations"] += 1
        self.session.flush()
        return JobNormalizationResult(counts=counts, reason_codes=["unresolved_job_references"] if unresolved else [])

    def _verification_status(self, job: JobPosting, evidence: dict[str, Any], flags: list[str]) -> str:
        now = datetime.now(timezone.utc)
        valid_through = job.valid_through
        if valid_through is not None and valid_through.tzinfo is None:
            valid_through = valid_through.replace(tzinfo=timezone.utc)
        if valid_through and valid_through < now:
            return "expired"
        if evidence.get("http_status") in {404, 410} or evidence.get("closed_signal_found"):
            return "closed"
        if not evidence.get("page_accessible") or not evidence.get("apply_route_available"):
            return "apply_unavailable"
        has_future_deadline = valid_through is not None and valid_through >= now
        if job.date_posted is None and not has_future_deadline:
            flags.append("missing_date_posted")
            return "needs_review"
        if job.date_posted is None:
            flags.append("missing_date_posted")
        trusted = job.source_kind == "employer" or (
            job.source_kind == "ats" and evidence.get("employer_identity_match", False)
        )
        source = next((item for item in self.session.exec(select(JobSourceTrust).where(JobSourceTrust.enabled == True)).all() if job.source_domain == item.domain or job.source_domain.endswith(f".{item.domain}")), None)  # noqa: E712
        if source and source.trust_level == "blocked":
            flags.append("blocked_source")
            return "needs_review"
        if source and source.trust_level == "verification_capable":
            trusted = job.source_kind == "trusted_portal" or evidence.get("employer_identity_match", False)
        if not trusted:
            flags.append("untrusted_verification_source")
            return "needs_review"
        return "verified_open"
