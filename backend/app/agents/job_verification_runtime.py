from __future__ import annotations

import json
import time
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, select

from backend.app.agents.company_research_runtime import CompanyResearchRuntime, _utc_now
from backend.app.agents.job_verification import (
    JOB_VERIFICATION_INSTRUCTIONS,
    build_job_verification_inputs,
    build_job_verification_task,
)
from backend.app.agents.run_folder import RunFolderGenerator, RunFolderSpec, RunInputFile
from backend.app.core.config import Settings
from backend.app.db import session as db_session_module
from backend.app.db.models import Campaign, JobPosting, JobSourceTrust, MasterCvProfileSnapshot, PolicySnapshot, Run, UserProfileSnapshot
from backend.app.imports.import_service import JOB_VERIFICATION_RUN_TYPE, RunImportService
from backend.app.jobs.sources import BUILTIN_JOB_SOURCES
from backend.app.agents.pi_runtime import build_restricted_pi_rpc_command


class JobVerificationRuntime(CompanyResearchRuntime):
    def _ensure_prepared_run(self, run_id: str) -> None:
        with Session(db_session_module.engine) as session:
            run = session.exec(select(Run).where(Run.run_id == run_id)).first()
            if run is None or run.agent_type != JOB_VERIFICATION_RUN_TYPE:
                raise ValueError(f"Job verification run is not prepared: {run_id}")

    def _prepare_workspace(self, run_id: str) -> Path:
        root = self._run_root(run_id)
        workspace = root / "workspace"
        for dirname in ("input", "output", "logs", "workspace", "output/jobs", "output/job_fit_evaluations"):
            (root / dirname).mkdir(parents=True, exist_ok=True)
        (workspace / "AGENTS.md").write_text(JOB_VERIFICATION_INSTRUCTIONS, encoding="utf-8")
        (workspace / "README.md").write_text(
            "# Vacancy Verifier Workspace\n\nVerify only the supplied vacancy. This workspace has no discovery task.\n",
            encoding="utf-8",
        )
        return workspace

    def _prompt(self, run_id: str) -> str:
        root = self._run_root(run_id)
        return (
            "Run the prepared Vacancy Verifier task now. Do not perform vacancy discovery or search for other jobs.\n\n"
            + "Instructions:\n"
            + (root / "instructions.md").read_text(encoding="utf-8")
            + "\n\nTask:\n"
            + (root / "task.md").read_text(encoding="utf-8")
            + "\nNavigate only to the URLs supplied in target_job.json and directly necessary same-employer context. "
            "Write only the selected job and its matching fit JSON. Never contact or apply."
        )

    def _command(self, run_id: str) -> list[str]:
        return build_restricted_pi_rpc_command(
            binary=self.settings.pi_rpc_binary,
            session_dir=self._session_dir(run_id),
            extension_path=self.settings.pi_rpc_job_verification_extension_path,
            provider=self.settings.pi_rpc_research_provider,
            model=self.settings.pi_rpc_job_verification_model,
            thinking=self.settings.pi_rpc_research_thinking,
        )

    def _run_agent(self, run_id: str) -> None:
        started = time.monotonic()
        try:
            client = self._client(run_id)
            result = client.prompt(self._prompt(run_id), timeout_seconds=min(900, self._prompt_timeout_seconds(run_id)))
            for event in result.events:
                self._append_event(run_id, event)
            counts = self._artifact_counts(run_id)
            self._validate_verification_outputs(run_id)
            self._write_state(run_id, "importing", last_reply=result.text, artifact_counts=counts, elapsed_seconds=round(time.monotonic() - started, 3))
            with Session(db_session_module.engine) as session:
                imported = RunImportService(session=session, settings=self.settings).import_run(run_id, run_type=JOB_VERIFICATION_RUN_TYPE)
            self._write_state(run_id, imported.run.status, artifact_counts=counts, imported_at=_utc_now())
        except Exception as exc:
            self._write_state(run_id, "failed", last_error=str(exc), error_type=type(exc).__name__, failed_at=_utc_now())
            self._mark_run(run_id, "research_failed", action="job_verification_failed", result_status="failed", reason_codes=["runtime_error"])
        finally:
            client = self.clients.pop(run_id, None)
            if client is not None:
                client.close()

    def _artifact_counts(self, run_id: str) -> dict[str, int]:
        output = self._run_root(run_id) / "output"
        jobs = len(list((output / "jobs").glob("*.json")))
        fits = len(list((output / "job_fit_evaluations").glob("*.json")))
        return {"companies": 0, "jobs": jobs, "contacts": 0, "fit_evaluations": fits, "job_fit_evaluations": fits, "unexpected": 0}

    def _validate_verification_outputs(self, run_id: str) -> None:
        root = self._run_root(run_id)
        target = json.loads((root / "input" / "target_job.json").read_text(encoding="utf-8"))
        target_id = target.get("job_id")
        job_files = list((root / "output" / "jobs").glob("*.json"))
        fit_files = list((root / "output" / "job_fit_evaluations").glob("*.json"))
        job_ids = [json.loads(path.read_text(encoding="utf-8")).get("job_id") for path in job_files]
        fit_ids = [json.loads(path.read_text(encoding="utf-8")).get("job_id") for path in fit_files]
        unexpected = [path for path in (root / "output").rglob("*.json") if path.parent.name not in {"jobs", "job_fit_evaluations"}]
        if unexpected or job_ids != [target_id] or fit_ids != [target_id]:
            raise ValueError("Vacancy verifier contract requires exactly the selected job and its matching fit evaluation.")


def prepare_job_verification_run(*, campaign: Campaign, job: JobPosting, session: Session, settings: Settings) -> str:
    def approved(model, pk):
        item = session.get(model, pk) if pk else None
        if item is None:
            raise ValueError("Job verification requires approved campaign snapshots.")
        return item

    profile = approved(UserProfileSnapshot, campaign.user_profile_snapshot_id)
    master_cv = approved(MasterCvProfileSnapshot, campaign.master_cv_profile_snapshot_id)
    policy = approved(PolicySnapshot, campaign.policy_snapshot_id)
    sources_by_domain = {item.domain: item for item in session.exec(select(JobSourceTrust)).all()}
    for domain, trust_level in BUILTIN_JOB_SOURCES.items():
        if domain not in sources_by_domain:
            source = JobSourceTrust(domain=domain, trust_level=trust_level, is_builtin=True, workspace_id=campaign.workspace_id)
            session.add(source)
            sources_by_domain[domain] = source
    session.flush()
    target = {
        "job_id": job.job_id,
        "company_id": job.external_company_id,
        "title": job.title,
        "canonical_url": job.canonical_url,
        "application_url": job.application_url,
        "source_url": job.source_url,
        "source_domain": job.source_domain,
        "source_kind": job.source_kind,
        "date_posted": job.date_posted.isoformat() if job.date_posted else None,
        "valid_through": job.valid_through.isoformat() if job.valid_through else None,
    }
    inputs = build_job_verification_inputs(
        job=target,
        user_profile=json.loads(profile.raw_json),
        master_cv_profile=json.loads(master_cv.raw_json),
        policy=json.loads(policy.raw_json),
        trusted_sources=[{"domain": item.domain, "trust_level": item.trust_level, "enabled": item.enabled} for item in sources_by_domain.values()],
        schemas={name: (settings.schemas_root / name).read_text(encoding="utf-8") for name in ("job_posting_candidate.schema.json", "job_fit_evaluation.schema.json")},
    )
    run_id = f"job-verification-{campaign.campaign_id}-{int(time.time())}-{uuid4().hex[:8]}"
    RunFolderGenerator(settings=settings, session=session).prepare(
        RunFolderSpec(
            run_id=run_id,
            task=build_job_verification_task(target),
            instructions=JOB_VERIFICATION_INSTRUCTIONS,
            inputs=tuple(RunInputFile(path, content) for path, content in sorted(inputs.items())),
            expected_output_files=("jobs/*.json", "job_fit_evaluations/*.json"),
            metadata={"task_type": JOB_VERIFICATION_RUN_TYPE, "campaign_id": campaign.campaign_id, "target_job_id": job.job_id},
        )
    )
    run = session.exec(select(Run).where(Run.run_id == run_id)).first()
    if run:
        run.agent_type = JOB_VERIFICATION_RUN_TYPE
        session.add(run)
        session.commit()
    return run_id
