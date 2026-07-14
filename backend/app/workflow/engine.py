from __future__ import annotations

import hashlib
import json
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from backend.app.auth.context import RequestIdentity, scoped_runs_root, workspace_context
from backend.app.core.config import Settings, get_settings
from backend.app.db import session as db_session_module
from backend.app.db.models import (
    AgentTask,
    Campaign,
    CampaignCompany,
    CampaignJob,
    Company,
    Contact,
    Document,
    EmailDraft,
    FitEvaluation,
    JobPosting,
    JobApplicationPackage,
    ImportedFile,
    ReviewException,
    SendIntent,
    User,
    Workspace,
    utc_now,
)
from backend.app.monitoring.issues import record_issue


TERMINAL_RUNTIME_STATUSES = {"imported", "imported_with_errors", "import_failed", "research_failed", "failed"}
FAILED_RUNTIME_STATUSES = {"import_failed", "research_failed", "failed"}
_worker: "WorkflowWorker | None" = None


def json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


class WorkflowEngine:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self.session = session
        self.settings = settings or get_settings()

    def enqueue(
        self,
        *,
        campaign: Campaign,
        task_type: str,
        agent_role: str,
        company: Company | None = None,
        payload: dict[str, Any] | None = None,
        narrative: str,
    ) -> AgentTask:
        existing = self.session.exec(
            select(AgentTask).where(
                AgentTask.campaign_id == campaign.id,
                AgentTask.company_id == (company.id if company else None),
                AgentTask.task_type == task_type,
                AgentTask.status.in_(["queued", "retry", "running", "completed"]),
            )
        ).first()
        if existing is not None:
            return existing
        task = AgentTask(
            task_id=f"task-{uuid4()}",
            campaign_id=campaign.id,
            company_id=company.id if company else None,
            agent_role=agent_role,
            task_type=task_type,
            narrative=narrative,
            input_json=json.dumps(payload or {}, sort_keys=True),
            workspace_id=campaign.workspace_id,
        )
        self.session.add(task)
        self.session.commit()
        self.session.refresh(task)
        return task

    def process(self, task: AgentTask) -> None:
        task.status = "running"
        task.started_at = task.started_at or utc_now()
        task.locked_at = utc_now()
        task.locked_by = "local-workflow-worker"
        task.attempt_count += 1
        task.progress = max(task.progress, 5)
        task.updated_at = utc_now()
        self.session.add(task)
        self.session.commit()
        try:
            if task.task_type == "company_research":
                self._launch_research(task)
            elif task.task_type == "job_research":
                self._launch_job_research(task)
            elif task.task_type == "contact_research":
                self._launch_contact_research(task)
            elif task.task_type == "application_draft":
                self._launch_application_draft(task)
            elif task.task_type == "job_application_draft":
                self._launch_job_application_draft(task)
            elif task.task_type == "gated_send":
                self._send_application(task)
            else:
                raise ValueError(f"Unsupported workflow task type: {task.task_type}")
        except Exception as exc:
            self._fail(task, exc)

    def reconcile(self, task: AgentTask) -> None:
        try:
            if task.task_type == "company_research":
                from backend.app.agents.company_research_runtime import CompanyResearchRuntime

                status = CompanyResearchRuntime(settings=self.settings).status(task.run_id or "")
                self._reconcile_research(task, status)
            elif task.task_type == "job_research":
                from backend.app.agents.job_research_runtime import JobResearchRuntime
                self._reconcile_job_research(task, JobResearchRuntime(settings=self.settings).status(task.run_id or ""))
            elif task.task_type == "contact_research":
                from backend.app.agents.company_research_runtime import CompanyResearchRuntime

                status = CompanyResearchRuntime(settings=self.settings).status(task.run_id or "")
                self._reconcile_contact_research(task, status)
            elif task.task_type == "application_draft":
                from backend.app.agents.application_draft_runtime import ApplicationDraftRuntime

                status = ApplicationDraftRuntime(settings=self.settings).status(task.run_id or "")
                self._reconcile_draft(task, status)
            elif task.task_type == "job_application_draft":
                from backend.app.agents.application_draft_runtime import ApplicationDraftRuntime
                self._reconcile_job_application_draft(task, ApplicationDraftRuntime(settings=self.settings).status(task.run_id or ""))
        except Exception as exc:
            self._fail(task, exc)

    def _launch_research(self, task: AgentTask) -> None:
        from backend.app.agents.company_research_runtime import CompanyResearchRuntime
        from backend.app.api.routes import prepare_company_research_campaign
        from backend.app.schemas.api import CompanyResearchCampaignRequest

        campaign = self.session.get(Campaign, task.campaign_id)
        if campaign is None:
            raise ValueError("Campaign no longer exists.")
        brief = json_object(campaign.brief_json)
        request = CompanyResearchCampaignRequest(
            run_id=f"campaign-{campaign.campaign_id}-{uuid4().hex[:8]}",
            role_focus=str(brief.get("role_focus") or "Profile-aligned roles"),
            locations=[str(item) for item in brief.get("locations", [])],
            time_budget_minutes=int(brief.get("time_budget_minutes") or 30),
            max_companies=int(brief.get("max_companies") or 30),
            notes=str(brief.get("notes")) if brief.get("notes") else None,
        )
        prepared = prepare_company_research_campaign(request, session=self.session, settings=self.settings)
        CompanyResearchRuntime(settings=self.settings).launch(prepared.run_id)
        task.run_id = prepared.run_id
        task.progress = 15
        task.narrative = "The research agent is discovering and evaluating companies."
        task.output_json = json.dumps({"run_id": prepared.run_id})
        task.updated_at = utc_now()
        campaign.status = "researching"
        campaign.started_at = campaign.started_at or utc_now()
        campaign.updated_at = utc_now()
        self.session.add(task)
        self.session.add(campaign)
        self.session.commit()

    def _launch_job_research(self, task: AgentTask) -> None:
        from backend.app.agents.job_research_runtime import JobResearchRuntime, prepare_job_research_run

        campaign = self.session.get(Campaign, task.campaign_id)
        if campaign is None or campaign.campaign_type != "listed_job_search":
            raise ValueError("Job research requires a listed-job campaign.")
        run_id = prepare_job_research_run(campaign=campaign, session=self.session, settings=self.settings)
        JobResearchRuntime(settings=self.settings).launch(run_id)
        task.run_id = run_id
        task.progress = 15
        task.narrative = "The vacancy scout is searching broad sources and verifying application routes."
        task.output_json = json.dumps({"run_id": run_id})
        task.updated_at = utc_now()
        campaign.status = "researching"
        campaign.updated_at = utc_now()
        self.session.add_all([task, campaign])
        self.session.commit()

    def _launch_application_draft(self, task: AgentTask) -> None:
        from backend.app.agents.application_draft_runtime import ApplicationDraftRuntime
        from backend.app.api.routes import _prepare_application_draft_response
        from backend.app.schemas.api import ApplicationDraftRequest

        company = self.session.get(Company, task.company_id)
        if company is None:
            raise ValueError("Company no longer exists.")
        prepared = _prepare_application_draft_response(
            ApplicationDraftRequest(company_id=company.company_id),
            session=self.session,
            settings=self.settings,
        )
        ApplicationDraftRuntime(settings=self.settings).launch(prepared.run_id)
        task.run_id = prepared.run_id
        task.progress = 20
        task.narrative = f"The CV and writing specialists are preparing {company.name}."
        task.output_json = json.dumps({"run_id": prepared.run_id, "draft_id": prepared.draft_id})
        task.updated_at = utc_now()
        link = self._campaign_company(task.campaign_id, company.id)
        if link is not None:
            link.stage = "preparing"
            link.entered_stage_at = utc_now()
            link.updated_at = utc_now()
            self.session.add(link)
        self.session.add(task)
        self.session.commit()

    def _launch_job_application_draft(self, task: AgentTask) -> None:
        from backend.app.agents.application_draft_runtime import ApplicationDraftRuntime
        from backend.app.jobs.application_packages import JobApplicationPackageService

        payload = json_object(task.input_json)
        campaign = self.session.get(Campaign, task.campaign_id)
        job = self.session.exec(select(JobPosting).where(JobPosting.job_id == payload.get("job_id"))).first()
        company = self.session.get(Company, task.company_id) if task.company_id else None
        if campaign is None or job is None or company is None:
            raise ValueError("Listed-job application context no longer exists.")
        run_id = JobApplicationPackageService(self.session, self.settings).prepare_agent_run(
            campaign=campaign, job=job, company=company
        )
        ApplicationDraftRuntime(settings=self.settings).launch(run_id)
        task.run_id = run_id
        task.progress = 20
        task.narrative = f"The CV and writing specialists are tailoring the application to {job.title}."
        task.output_json = json.dumps({"run_id": run_id, "job_id": job.job_id})
        task.updated_at = utc_now()
        self.session.add(task)
        self.session.commit()

    def _launch_contact_research(self, task: AgentTask) -> None:
        from backend.app.agents.company_research_runtime import CompanyResearchRuntime
        from backend.app.api.routes import prepare_company_research_campaign
        from backend.app.schemas.api import CompanyResearchCampaignRequest

        company = self.session.get(Company, task.company_id)
        if company is None:
            raise ValueError("Company no longer exists.")
        request = CompanyResearchCampaignRequest(
            run_id=f"contact-{company.company_id}-{uuid4().hex[:8]}",
            role_focus="Contact research only",
            locations=[],
            time_budget_minutes=10,
            max_companies=1,
            notes=(
                f"Refresh the existing company {company.name} "
                f"({company.company_id}, {company.normalized_domain or company.raw_domain or 'domain unavailable'}). "
                "Research only this company and find a public, professional recruiting or careers email. "
                "Write the company candidate needed to preserve the company reference and write a contact candidate "
                "only when a suitable, sourced address is found. Do not discover other companies."
            ),
        )
        prepared = prepare_company_research_campaign(request, session=self.session, settings=self.settings)
        CompanyResearchRuntime(settings=self.settings).launch(prepared.run_id)
        task.run_id = prepared.run_id
        task.progress = 20
        task.narrative = f"The research specialist is looking for a suitable public contact at {company.name}."
        task.output_json = json.dumps({"run_id": prepared.run_id})
        task.updated_at = utc_now()
        self.session.add(task)
        self.session.commit()

    def _send_application(self, task: AgentTask) -> None:
        from backend.app.email_delivery.batch_send import SendBatchService

        campaign = self.session.get(Campaign, task.campaign_id)
        company = self.session.get(Company, task.company_id)
        if campaign is None or company is None:
            raise ValueError("Campaign company no longer exists.")
        if campaign.sending_mode != "gated_autosend":
            self._complete(task, "Application is ready; this campaign stops at drafts.")
            return
        intent = self.session.exec(
            select(SendIntent)
            .where(SendIntent.company_id == company.id)
            .order_by(SendIntent.created_at.desc())
        ).first()
        if intent is None:
            raise ValueError("No validated send intent is available yet.")
        result = SendBatchService(self.session, settings=self.settings).approve_and_send(
            [intent.intent_id],
            reviewer_id=f"autopilot:{campaign.campaign_id}",
        )
        if result.sent_count != 1:
            detail = result.items[0].detail or ", ".join(result.items[0].reason_codes) or result.items[0].status
            raise ValueError(f"The backend gate did not deliver this outreach: {detail}")
        link = self._campaign_company(campaign.id, company.id)
        if link is not None:
            link.stage = "sent"
            link.entered_stage_at = utc_now()
            link.updated_at = utc_now()
            self.session.add(link)
        self._complete(task, f"Outreach to {company.name} passed the gate and was sent.")

    def _reconcile_research(self, task: AgentTask, status: dict[str, Any]) -> None:
        state = str(status.get("status") or "running")
        counts = status.get("artifact_counts") or {}
        task.progress = min(90, max(task.progress, int(counts.get("companies", 0)) * 2))
        task.narrative = f"Research found {int(counts.get('companies', 0))} companies and is checking fit."
        task.updated_at = utc_now()
        self.session.add(task)
        if state not in TERMINAL_RUNTIME_STATUSES:
            self.session.commit()
            return
        if state in FAILED_RUNTIME_STATUSES:
            raise ValueError(f"Company research ended with {state}.")
        campaign = self.session.get(Campaign, task.campaign_id)
        if campaign is None:
            raise ValueError("Campaign no longer exists.")
        file_ids = self.session.exec(select(ImportedFile.id).where(ImportedFile.run_id == task.run_id)).all()
        companies = self.session.exec(select(Company).where(Company.imported_file_id.in_(file_ids))).all() if file_ids else []
        for company in companies:
            link = self._campaign_company(campaign.id, company.id)
            if link is None:
                conflicts = json.loads(company.policy_conflicts_json or "[]")
                link = CampaignCompany(
                    campaign_id=campaign.id,
                    company_id=company.id,
                    stage="archived" if conflicts else "qualified",
                    disposition="policy_excluded" if conflicts else None,
                    stage_reason="Excluded by campaign policy." if conflicts else "Research and fit evidence imported.",
                )
                self.session.add(link)
                self.session.flush()
            if link.stage != "archived":
                contact = self._latest_contact(company.id)
                if contact is None:
                    self.enqueue(
                        campaign=campaign,
                        company=company,
                        task_type="contact_research",
                        agent_role="contact_researcher",
                        narrative=f"Finding a suitable public recruiting contact for {company.name}.",
                    )
                else:
                    self._enqueue_application_draft(campaign, company)
        campaign.status = "preparing"
        campaign.updated_at = utc_now()
        self.session.add(campaign)
        self._complete(task, f"Research completed with {len(companies)} companies ready for the next specialist.")

    def _reconcile_job_research(self, task: AgentTask, status: dict[str, Any]) -> None:
        state = str(status.get("status") or "running")
        counts = status.get("artifact_counts") or {}
        task.progress = min(90, max(task.progress, int(counts.get("jobs", 0)) * 3))
        task.narrative = f"Vacancy research found {int(counts.get('jobs', 0))} listings and is checking validity and fit."
        task.updated_at = utc_now()
        self.session.add(task)
        if state not in TERMINAL_RUNTIME_STATUSES:
            self.session.commit()
            return
        if state in FAILED_RUNTIME_STATUSES:
            raise ValueError(f"Job research ended with {state}.")
        campaign = self.session.get(Campaign, task.campaign_id)
        if campaign is None:
            raise ValueError("Campaign no longer exists.")
        file_ids = self.session.exec(select(ImportedFile.id).where(ImportedFile.run_id == task.run_id)).all()
        jobs = self.session.exec(select(JobPosting).where(JobPosting.imported_file_id.in_(file_ids))).all() if file_ids else []
        for job in jobs:
            link = self.session.exec(select(CampaignJob).where(CampaignJob.campaign_id == campaign.id, CampaignJob.job_posting_id == job.id)).first()
            if link is None:
                self.session.add(CampaignJob(campaign_id=campaign.id, job_posting_id=job.id, application_status="discovered"))
        campaign.status = "active"
        campaign.updated_at = utc_now()
        self.session.add(campaign)
        self._complete(task, f"Vacancy research completed with {len(jobs)} listings retained with verification evidence.")

    def _reconcile_contact_research(self, task: AgentTask, status: dict[str, Any]) -> None:
        state = str(status.get("status") or "running")
        task.progress = 70 if state not in TERMINAL_RUNTIME_STATUSES else task.progress
        task.updated_at = utc_now()
        self.session.add(task)
        if state not in TERMINAL_RUNTIME_STATUSES:
            self.session.commit()
            return
        if state in FAILED_RUNTIME_STATUSES:
            raise ValueError(f"Contact research ended with {state}.")
        campaign = self.session.get(Campaign, task.campaign_id)
        company = self.session.get(Company, task.company_id)
        if campaign is None or company is None:
            raise ValueError("Campaign company no longer exists.")
        contact = self._latest_contact(company.id)
        if contact is None:
            self._block_no_contact(task, company)
            return
        self._enqueue_application_draft(campaign, company)
        self._complete(task, f"A suitable public contact for {company.name} was imported; application preparation is queued.")

    def _enqueue_application_draft(self, campaign: Campaign, company: Company) -> AgentTask:
        return self.enqueue(
            campaign=campaign,
            company=company,
            task_type="application_draft",
            agent_role="resume_and_email_team",
            narrative=f"Preparing a tailored application for {company.name}.",
        )

    def _latest_contact(self, company_id: int | None) -> Contact | None:
        if company_id is None:
            return None
        return self.session.exec(
            select(Contact).where(Contact.company_id == company_id).order_by(Contact.created_at.desc())
        ).first()

    def _block_no_contact(self, task: AgentTask, company: Company) -> None:
        task.status = "blocked"
        task.progress = 100
        task.last_error = f"No suitable public professional contact was found for {company.name}."
        task.narrative = task.last_error
        task.completed_at = utc_now()
        task.locked_at = None
        task.locked_by = None
        task.updated_at = utc_now()
        self.session.add(task)
        self.session.add(
            ReviewException(
                exception_id=f"exception-{uuid4()}",
                campaign_id=task.campaign_id,
                company_id=company.id,
                agent_task_id=task.id,
                category="contact_not_found",
                title=f"No suitable contact found for {company.name}",
                explanation=(
                    f"Contact research completed for {company.name}, but no schema-valid, sourced public professional "
                    "email address was imported. Application drafting has not been started."
                ),
                recommended_action="Retry contact research with new guidance or skip this company.",
            )
        )
        self.session.commit()

    def _reconcile_draft(self, task: AgentTask, status: dict[str, Any]) -> None:
        state = str(status.get("status") or "running")
        task.progress = 70 if state not in TERMINAL_RUNTIME_STATUSES else task.progress
        task.updated_at = utc_now()
        self.session.add(task)
        if state not in TERMINAL_RUNTIME_STATUSES:
            self.session.commit()
            return
        if state in FAILED_RUNTIME_STATUSES:
            raise ValueError(f"Application preparation ended with {state}.")
        campaign = self.session.get(Campaign, task.campaign_id)
        company = self.session.get(Company, task.company_id)
        if campaign is None or company is None:
            raise ValueError("Campaign company no longer exists.")
        draft = self.session.exec(
            select(EmailDraft).where(EmailDraft.company_id == company.id).order_by(EmailDraft.created_at.desc())
        ).first()
        if draft is None:
            raise ValueError("The agent run completed without an imported email draft.")
        link = self._campaign_company(campaign.id, company.id)
        if link is not None:
            link.stage = "ready"
            link.entered_stage_at = utc_now()
            link.updated_at = utc_now()
            self.session.add(link)
        self._index_documents(task, company)
        if campaign.sending_mode == "gated_autosend":
            self.enqueue(
                campaign=campaign,
                company=company,
                task_type="gated_send",
                agent_role="delivery_coordinator",
                narrative=f"Running final deterministic checks for {company.name}.",
            )
        self._complete(task, f"The tailored CV and email for {company.name} are ready.")

    def _reconcile_job_application_draft(self, task: AgentTask, status: dict[str, Any]) -> None:
        state = str(status.get("status") or "running")
        task.progress = 70 if state not in TERMINAL_RUNTIME_STATUSES else task.progress
        task.updated_at = utc_now()
        self.session.add(task)
        if state not in TERMINAL_RUNTIME_STATUSES:
            self.session.commit()
            return
        if state in FAILED_RUNTIME_STATUSES:
            raise ValueError(f"Listed-job application preparation ended with {state}.")
        payload = json_object(task.input_json)
        job = self.session.exec(select(JobPosting).where(JobPosting.job_id == payload.get("job_id"))).first()
        campaign = self.session.get(Campaign, task.campaign_id)
        company = self.session.get(Company, task.company_id) if task.company_id else None
        if campaign is None or job is None or company is None:
            raise ValueError("Listed-job application context no longer exists.")
        link = self.session.exec(select(CampaignJob).where(
            CampaignJob.campaign_id == campaign.id, CampaignJob.job_posting_id == job.id
        )).first()
        if link is None:
            raise ValueError("Job is no longer part of the campaign.")
        file_ids = self.session.exec(select(ImportedFile.id).where(ImportedFile.run_id == task.run_id)).all()
        draft = self.session.exec(select(EmailDraft).where(EmailDraft.imported_file_id.in_(file_ids)).order_by(EmailDraft.created_at.desc())).first() if file_ids else None
        if draft is None:
            raise ValueError("The drafting agent completed without a schema-valid cover letter.")
        self._index_documents(task, company)
        self.session.flush()
        cv_document = self.session.exec(select(Document).where(
            Document.run_id == task.run_id, Document.document_type == "tailored_cv", Document.mime_type == "application/pdf"
        )).first()
        review_flags = json.loads(draft.review_flags_json or "[]")
        package = JobApplicationPackage(
            package_id=f"package-{uuid4()}", campaign_job_id=link.id, run_id=task.run_id,
            status="ready_with_review" if review_flags else "ready",
            cv_document_id=cv_document.id if cv_document else None,
            cover_letter_text=draft.body_text,
            answer_kit_json="[]", claim_refs_json=draft.claim_refs_json,
            review_flags_json=draft.review_flags_json, workspace_id=campaign.workspace_id,
        )
        link.application_status = "ready"
        link.updated_at = utc_now()
        self.session.add_all([package, link])
        self._complete(task, f"The vacancy-tailored CV and cover letter for {job.title} are ready.")

    def _index_documents(self, task: AgentTask, company: Company) -> None:
        if not task.run_id:
            return
        output = scoped_runs_root(self.settings.runs_root) / task.run_id / "output"
        if not output.is_dir():
            return
        for path in output.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".pdf", ".html", ".htm", ".json", ".txt"}:
                continue
            relative = path.relative_to(scoped_runs_root(self.settings.runs_root)).as_posix()
            existing = self.session.exec(select(Document).where(Document.relative_path == relative)).first()
            if existing is not None:
                continue
            data = path.read_bytes()
            kind = "tailored_cv" if "cv" in path.name.lower() or path.suffix.lower() == ".pdf" else "email_draft"
            mime = "application/pdf" if path.suffix.lower() == ".pdf" else "text/html" if path.suffix.lower() in {".html", ".htm"} else "application/json" if path.suffix.lower() == ".json" else "text/plain"
            self.session.add(
                Document(
                    document_id=f"document-{uuid4()}",
                    campaign_id=task.campaign_id,
                    company_id=company.id,
                    run_id=task.run_id,
                    document_type=kind,
                    title=f"{company.name} — {'Tailored CV' if kind == 'tailored_cv' else 'Email draft'}",
                    filename=path.name,
                    relative_path=relative,
                    mime_type=mime,
                    size_bytes=len(data),
                    content_hash=hashlib.sha256(data).hexdigest(),
                    provenance_json=json.dumps({"agent_task_id": task.task_id, "run_id": task.run_id}),
                )
            )

    def _complete(self, task: AgentTask, narrative: str) -> None:
        task.status = "completed"
        task.progress = 100
        task.narrative = narrative
        task.completed_at = utc_now()
        task.locked_at = None
        task.locked_by = None
        task.updated_at = utc_now()
        self.session.add(task)
        self.session.commit()

    def _fail(self, task: AgentTask, exc: Exception) -> None:
        task.last_error = str(exc)
        task.locked_at = None
        task.locked_by = None
        task.updated_at = utc_now()
        if task.attempt_count < task.max_attempts:
            task.status = "retry"
            task.available_at = utc_now() + timedelta(seconds=min(300, 5 * (2 ** task.attempt_count)))
            task.narrative = "A specialist hit a problem and will retry automatically."
        else:
            task.status = "blocked"
            task.narrative = "The specialist could not resolve this without your help."
            record_issue(
                "workflow_task_blocked",
                str(exc),
                source=task.task_id,
                details={"agent_role": task.agent_role, "task_type": task.task_type},
            )
            self.session.add(
                ReviewException(
                    exception_id=f"exception-{uuid4()}",
                    campaign_id=task.campaign_id,
                    company_id=task.company_id,
                    agent_task_id=task.id,
                    category="agent_failure",
                    title="A specialist needs help continuing",
                    explanation=str(exc),
                    recommended_action="Review the context, then retry this step or skip the company.",
                )
            )
        self.session.add(task)
        self.session.commit()

    def _campaign_company(self, campaign_id: int | None, company_id: int | None) -> CampaignCompany | None:
        if campaign_id is None or company_id is None:
            return None
        return self.session.exec(
            select(CampaignCompany).where(
                CampaignCompany.campaign_id == campaign_id,
                CampaignCompany.company_id == company_id,
            )
        ).first()


class WorkflowWorker:
    def __init__(self, settings: Settings | None = None, poll_seconds: float = 3.0) -> None:
        self.settings = settings or get_settings()
        self.poll_seconds = poll_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="auto-initiativ-workflow", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def run_once(self) -> bool:
        with Session(db_session_module.engine) as session:
            running = session.exec(
                select(AgentTask).where(
                    AgentTask.status == "running",
                    AgentTask.task_type.in_(["company_research", "job_research", "contact_research", "application_draft"]),
                ).order_by(AgentTask.updated_at)
            ).first()
            task = running or session.exec(
                select(AgentTask).where(
                    AgentTask.status.in_(["queued", "retry"]),
                    AgentTask.available_at <= utc_now(),
                ).order_by(AgentTask.available_at, AgentTask.created_at)
            ).first()
            if task is None or task.workspace_id is None:
                return False
            workspace = session.get(Workspace, task.workspace_id)
            user = session.get(User, workspace.owner_user_id) if workspace is not None else None
            if workspace is None or user is None:
                return False
            identity = RequestIdentity(user_id=user.id, workspace_id=workspace.id, role=user.role)
            task_id = task.id
        with workspace_context(identity), Session(db_session_module.engine) as scoped_session:
            scoped_task = scoped_session.get(AgentTask, task_id)
            if scoped_task is None:
                return False
            engine = WorkflowEngine(scoped_session, self.settings)
            if scoped_task.status == "running":
                engine.reconcile(scoped_task)
            else:
                engine.process(scoped_task)
        return True

    def _loop(self) -> None:
        while not self._stop.is_set():
            worked = False
            try:
                worked = self.run_once()
            except Exception as exc:
                record_issue(
                    "workflow_worker_error",
                    str(exc) or type(exc).__name__,
                    source="auto-initiativ-workflow",
                    details={"exception_type": type(exc).__name__},
                )
                worked = False
            self._stop.wait(0.25 if worked else self.poll_seconds)


def start_workflow_worker(settings: Settings | None = None) -> WorkflowWorker:
    global _worker
    if _worker is None:
        _worker = WorkflowWorker(settings)
    _worker.start()
    return _worker


def stop_workflow_worker() -> None:
    global _worker
    if _worker is not None:
        _worker.stop()
        _worker = None
