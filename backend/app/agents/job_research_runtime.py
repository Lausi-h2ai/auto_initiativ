from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from backend.app.agents.company_research_runtime import CompanyResearchRuntime, _utc_now
from backend.app.agents.job_research import JOB_RESEARCH_INSTRUCTIONS, JobResearchCampaign, build_job_research_inputs, build_job_research_task
from backend.app.agents.run_folder import RunFolderGenerator, RunFolderSpec, RunInputFile
from backend.app.core.config import Settings
from backend.app.db import session as db_session_module
from backend.app.db.models import Campaign, Company, JobPosting, JobSourceTrust, MasterCvProfileSnapshot, PolicySnapshot, Run, UserProfileSnapshot
from backend.app.imports.import_service import JOB_RESEARCH_RUN_TYPE, RunImportService
from backend.app.jobs.sources import BUILTIN_JOB_SOURCES


class JobResearchRuntime(CompanyResearchRuntime):
    def _ensure_prepared_run(self, run_id: str) -> None:
        with Session(db_session_module.engine) as session:
            run = session.exec(select(Run).where(Run.run_id == run_id)).first()
            if run is None or run.agent_type != JOB_RESEARCH_RUN_TYPE:
                raise ValueError(f"Job research run is not prepared: {run_id}")

    def _prepare_workspace(self, run_id: str) -> Path:
        run_root = self._run_root(run_id)
        workspace = run_root / "workspace"
        for dirname in ("input", "output", "logs", "workspace", "output/companies", "output/jobs", "output/job_fit_evaluations"):
            (run_root / dirname).mkdir(parents=True, exist_ok=True)
        (workspace / "AGENTS.md").write_text(JOB_RESEARCH_INSTRUCTIONS, encoding="utf-8")
        (workspace / "README.md").write_text("# Vacancy Scout Workspace\n\nSearch public sources broadly. Write only allowed structured research artifacts.\n", encoding="utf-8")
        return workspace

    def _prompt(self, run_id: str) -> str:
        root = self._run_root(run_id)
        return (
            "Run the prepared Vacancy Scout task now.\n\n"
            + (root / "instructions.md").read_text(encoding="utf-8")
            + "\n\n"
            + (root / "task.md").read_text(encoding="utf-8")
            + "\nUse the scoped research tools. Write company, job, and job-fit JSON artifacts only; never contact or apply."
        )

    def _run_agent(self, run_id: str) -> None:
        started = time.monotonic()
        try:
            client = self._client(run_id)
            result = client.prompt(self._prompt(run_id), timeout_seconds=self._prompt_timeout_seconds(run_id))
            for event in result.events:
                self._append_event(run_id, event)
            counts = self._artifact_counts(run_id)
            self._write_state(run_id, "importing", last_reply=result.text, artifact_counts=counts, elapsed_seconds=round(time.monotonic() - started, 3))
            with Session(db_session_module.engine) as session:
                imported = RunImportService(session=session, settings=self.settings).import_run(run_id, run_type=JOB_RESEARCH_RUN_TYPE)
            self._write_state(run_id, imported.run.status, artifact_counts=counts, imported_at=_utc_now())
        except Exception as exc:
            self._write_state(run_id, "failed", last_error=str(exc), error_type=type(exc).__name__, failed_at=_utc_now())
            self._mark_run(run_id, "research_failed", action="job_research_failed", result_status="failed", reason_codes=["runtime_error"])
        finally:
            client = self.clients.pop(run_id, None)
            if client is not None:
                client.close()

    def _artifact_counts(self, run_id: str) -> dict[str, int]:
        output = self._run_root(run_id) / "output"
        def count(name: str) -> int:
            folder = output / name
            return len(list(folder.glob("*.json"))) if folder.exists() else 0
        jobs = count("jobs")
        return {"companies": jobs, "jobs": jobs, "contacts": 0, "fit_evaluations": count("job_fit_evaluations"), "job_fit_evaluations": count("job_fit_evaluations"), "unexpected": 0}


def prepare_job_research_run(*, campaign: Campaign, session: Session, settings: Settings) -> str:
    def approved(model: type[Any], pk: int | None) -> Any:
        item = session.get(model, pk) if pk else None
        if item is None:
            raise ValueError("Job research requires approved campaign snapshots.")
        return item
    profile = approved(UserProfileSnapshot, campaign.user_profile_snapshot_id)
    master_cv = approved(MasterCvProfileSnapshot, campaign.master_cv_profile_snapshot_id)
    policy = approved(PolicySnapshot, campaign.policy_snapshot_id)
    brief = json.loads(campaign.brief_json or "{}")
    run_id = f"jobs-{campaign.campaign_id}-{int(time.time())}"
    spec = JobResearchCampaign(run_id=run_id, role_focus=str(brief.get("role_focus") or "Profile-aligned roles"), locations=[str(value) for value in brief.get("locations") or []], time_budget_minutes=int(brief.get("time_budget_minutes") or 30), max_jobs=int(brief.get("max_jobs") or 30), freshness_days=int(brief.get("freshness_days") or 30), filters={key: brief.get(key) for key in ("seniority", "employment_types", "work_modes", "minimum_salary", "languages")}, notes=brief.get("notes"))
    companies = [{"company_id": item.company_id, "name": item.name, "domain": item.normalized_domain or item.raw_domain} for item in session.exec(select(Company)).all()]
    jobs = [{"job_id": item.job_id, "canonical_url": item.canonical_url, "title": item.title, "company_id": item.external_company_id, "vacancy_status": item.vacancy_status} for item in session.exec(select(JobPosting)).all()]
    existing_sources = {item.domain: item for item in session.exec(select(JobSourceTrust)).all()}
    for domain, trust_level in BUILTIN_JOB_SOURCES.items():
        if domain not in existing_sources:
            source = JobSourceTrust(domain=domain, trust_level=trust_level, is_builtin=True, workspace_id=campaign.workspace_id)
            session.add(source)
            existing_sources[domain] = source
    session.flush()
    sources = [{"domain": item.domain, "trust_level": item.trust_level, "enabled": item.enabled} for item in existing_sources.values()]
    inputs = build_job_research_inputs(campaign=spec, user_profile=json.loads(profile.raw_json), master_cv_profile=json.loads(master_cv.raw_json), policy=json.loads(policy.raw_json), existing_companies=companies, existing_jobs=jobs, trusted_sources=sources, schemas={name: (settings.schemas_root / name).read_text(encoding="utf-8") for name in ("company_candidate.schema.json", "job_posting_candidate.schema.json", "job_fit_evaluation.schema.json")})
    RunFolderGenerator(settings=settings, session=session).prepare(RunFolderSpec(run_id=run_id, task=build_job_research_task(spec), instructions=JOB_RESEARCH_INSTRUCTIONS, inputs=tuple(RunInputFile(path, content) for path, content in sorted(inputs.items())), expected_output_files=("companies/*.json", "jobs/*.json", "job_fit_evaluations/*.json"), metadata={"task_type": JOB_RESEARCH_RUN_TYPE, "campaign_id": campaign.campaign_id, "target_job_count": spec.max_jobs}))
    run = session.exec(select(Run).where(Run.run_id == run_id)).first()
    if run:
        run.agent_type = JOB_RESEARCH_RUN_TYPE
        session.add(run)
        session.commit()
    return run_id
