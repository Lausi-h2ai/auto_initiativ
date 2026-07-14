from __future__ import annotations

import hashlib
import json
import re
from datetime import timedelta, timezone
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session

from backend.app.auth.context import scoped_runs_root
from backend.app.core.config import Settings
from backend.app.db.models import Campaign, CampaignJob, Document, JobApplicationPackage, JobPosting, MasterCvProfileSnapshot, UserProfileSnapshot, utc_now
from backend.app.imports.schema_registry import SchemaRegistry


class JobPackageError(ValueError):
    pass


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-ZÀ-ÿ0-9+#.-]{3,}", value.casefold())}


class JobApplicationPackageService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def prepare(self, *, campaign: Campaign, link: CampaignJob, job: JobPosting) -> JobApplicationPackage:
        if job.vacancy_status != "verified_open":
            raise JobPackageError("Application preparation requires a verified-open vacancy.")
        verified = job.last_verified_at
        if verified is None:
            raise JobPackageError("The vacancy has no verification timestamp.")
        if verified.tzinfo is None:
            verified = verified.replace(tzinfo=timezone.utc)
        if utc_now() - verified > timedelta(hours=24):
            job.vacancy_status = "stale"
            self.session.add(job)
            self.session.commit()
            raise JobPackageError("The vacancy must be revalidated because its verification is older than 24 hours.")
        master = self.session.get(MasterCvProfileSnapshot, campaign.master_cv_profile_snapshot_id)
        profile = self.session.get(UserProfileSnapshot, campaign.user_profile_snapshot_id)
        if master is None or profile is None:
            raise JobPackageError("Approved profile snapshots are unavailable.")
        master_data = json.loads(master.raw_json)
        profile_data = json.loads(profile.raw_json)
        target = _tokens(" ".join([job.title, job.description or "", job.requirements_json, job.responsibilities_json]))
        claims = [claim for claim in master_data.get("claims", []) if claim.get("approved_for_tailoring")]
        claims.sort(key=lambda claim: len(target & _tokens(" ".join([claim.get("statement", ""), " ".join(claim.get("tags") or [])]))), reverse=True)
        selected = claims[:10]
        claim_refs = [claim["claim_id"] for claim in selected]
        identity = profile_data.get("identity") or {}
        display_name = identity.get("display_name") or "Applicant"
        evidence_lines = [claim["statement"] for claim in selected[:3]]
        cover_letter = self._cover_letter(display_name, job, evidence_lines)
        answers = self._answers(profile_data, job, selected)
        review_flags = ["needs_user_input"] if any(item["needs_user_input"] for item in answers) else []
        run_id = f"job-package-{job.job_id}-{uuid4().hex[:8]}"
        output = scoped_runs_root(self.settings.runs_root) / run_id / "output"
        output.mkdir(parents=True, exist_ok=True)
        cv_payload = {"schema_version": "1.0", "job_id": job.job_id, "title": f"Tailored CV claims for {job.title}", "claim_refs": claim_refs, "claims": selected}
        cv_path = output / "tailored_cv.json"
        cv_path.write_text(json.dumps(cv_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        kit_payload = {"schema_version": "1.0", "package_id": f"package-{uuid4()}", "job_id": job.job_id, "cover_letter_text": cover_letter, "answers": answers, "claim_refs": claim_refs, "review_flags": review_flags}
        validation_errors = list(SchemaRegistry(self.settings.schemas_root).get_validator("application_answer_kit.schema.json").iter_errors(kit_payload))
        if validation_errors:
            raise JobPackageError(f"Application answer kit failed schema validation: {validation_errors[0].message}")
        (output / "application_answer_kit.json").write_text(json.dumps(kit_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        relative = cv_path.relative_to(scoped_runs_root(self.settings.runs_root)).as_posix()
        document = Document(document_id=f"document-{uuid4()}", campaign_id=campaign.id, company_id=job.company_id, run_id=run_id, document_type="tailored_cv", title=f"{job.title} — tailored CV claims", filename=cv_path.name, relative_path=relative, mime_type="application/json", size_bytes=cv_path.stat().st_size, content_hash=hashlib.sha256(cv_path.read_bytes()).hexdigest(), provenance_json=json.dumps({"job_id": job.job_id, "claim_refs": claim_refs}), workspace_id=campaign.workspace_id)
        self.session.add(document)
        self.session.flush()
        package = JobApplicationPackage(package_id=kit_payload["package_id"], campaign_job_id=link.id, run_id=run_id, status="ready_with_review" if review_flags else "ready", cv_document_id=document.id, cover_letter_text=cover_letter, answer_kit_json=json.dumps(answers), claim_refs_json=json.dumps(claim_refs), review_flags_json=json.dumps(review_flags), workspace_id=campaign.workspace_id)
        link.application_status = "ready"
        link.updated_at = utc_now()
        self.session.add_all([package, link])
        self.session.commit()
        self.session.refresh(package)
        return package

    def _cover_letter(self, name: str, job: JobPosting, evidence: list[str]) -> str:
        body = "\n\n".join(evidence) if evidence else "My approved profile contains relevant experience for this opportunity."
        return f"Dear Hiring Team,\n\nI am applying for the {job.title} position. {body}\n\nI would welcome the opportunity to discuss how this experience could support your team.\n\nKind regards,\n{name}"

    def _answers(self, profile: dict, job: JobPosting, claims: list[dict]) -> list[dict]:
        refs = [claim["claim_id"] for claim in claims[:3]]
        authorization = [item.get("value") for item in profile.get("work_authorization", []) if item.get("value")]
        availability = ((profile.get("preferences") or {}).get("availability") or {}).get("value")
        return [
            {"question": "Why are you interested in this role?", "answer": f"The {job.title} role aligns with my approved experience: " + "; ".join(claim.get("statement", "") for claim in claims[:3]), "claim_refs": refs, "needs_user_input": not bool(claims), "reason": "Uses approved profile claims only."},
            {"question": "What is your work authorization?", "answer": "; ".join(authorization), "claim_refs": [], "needs_user_input": not bool(authorization), "reason": "Confirm before submission."},
            {"question": "When can you start?", "answer": availability or "", "claim_refs": [], "needs_user_input": not bool(availability), "reason": "Confirm current availability before submission."},
            {"question": "What are your salary expectations?", "answer": "", "claim_refs": [], "needs_user_input": True, "reason": "Requires a current personal decision."},
        ]
