from __future__ import annotations

import hashlib
import json
import threading
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import or_, update
from sqlmodel import Session, select

from backend.app.auth.context import RequestIdentity, scoped_runs_root, workspace_context
from backend.app.core.config import Settings, get_settings
from backend.app.db import session as db_session_module
from backend.app.db.models import (
    AgentTask,
    AuditLog,
    Campaign,
    CampaignCompany,
    CampaignJob,
    Company,
    Contact,
    Document,
    EmailDraft,
    FitEvaluation,
    JobPosting,
    JobFitEvaluation,
    JobApplicationPackage,
    ImportedFile,
    ReviewException,
    ResearchDiscovery,
    ResearchPlan,
    ResearchSearchAttempt,
    ResearchTarget,
    SendIntent,
    User,
    Workspace,
    utc_now,
)
from backend.app.monitoring.issues import record_issue
from backend.app.localization import localized_text, workspace_locale


TERMINAL_RUNTIME_STATUSES = {"imported", "imported_with_errors", "import_failed", "research_failed", "failed"}
FAILED_RUNTIME_STATUSES = {"import_failed", "research_failed", "failed"}
SHARED_RESEARCH_LEASE_SECONDS = 120
SHARED_RESEARCH_LEASE_CANDIDATES = 2
MAX_SHARED_LEASES_PER_TARGET = 3
WORKFLOW_TASK_LEASE_SECONDS = 600
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

    def _text(self, workspace_id: int | None, english: str, german: str) -> str:
        return localized_text(workspace_locale(self.session, workspace_id), english, german)

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

    def process(self, task: AgentTask, *, already_claimed: bool = False) -> None:
        if already_claimed:
            if task.status != "running" or task.locked_by is None:
                raise ValueError("Workflow task must be atomically claimed before launch.")
        else:
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
            elif task.task_type in {"company_research_target", "job_research_target"}:
                self._launch_target_research(task)
            elif task.task_type == "job_verification":
                self._launch_job_verification(task)
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
            elif task.task_type in {"company_research_target", "job_research_target"}:
                from backend.app.agents.job_research_runtime import JobResearchRuntime
                from backend.app.agents.company_research_runtime import CompanyResearchRuntime

                runtime = JobResearchRuntime(settings=self.settings) if task.task_type == "job_research_target" else CompanyResearchRuntime(settings=self.settings)
                self._reconcile_target_research(task, runtime.status(task.run_id or ""))
            elif task.task_type == "job_verification":
                from backend.app.agents.job_verification_runtime import JobVerificationRuntime
                self._reconcile_job_verification(task, JobVerificationRuntime(settings=self.settings).status(task.run_id or ""))
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

    def block_uncertain_external_launch(self, task: AgentTask) -> None:
        message = (
            "A prior worker may have launched this task externally without persisting "
            "its run ID; automatic relaunch is blocked."
        )
        task.status = "blocked"
        task.last_error = message
        task.narrative = message
        task.locked_at = None
        task.locked_by = None
        task.completed_at = utc_now()
        task.updated_at = utc_now()
        self.session.add(task)
        self.session.add(
            ReviewException(
                exception_id=f"exception-{uuid4()}",
                campaign_id=task.campaign_id,
                company_id=task.company_id,
                agent_task_id=task.id,
                category="uncertain_external_launch",
                title="A specialist launch needs review",
                explanation=message,
                recommended_action="Inspect the external run state before retrying or skipping this task.",
            )
        )
        self.session.commit()

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
        task.narrative = self._text(task.workspace_id, "The research agent is discovering and evaluating companies.", "Der Recherche-Agent entdeckt und bewertet Unternehmen.")
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
        run_id = prepare_job_research_run(
            campaign=campaign,
            session=self.session,
            settings=self.settings,
        )
        JobResearchRuntime(settings=self.settings).launch(run_id)
        task.run_id = run_id
        task.progress = 15
        task.narrative = self._text(task.workspace_id, "The vacancy scout is searching broad sources and verifying application routes.", "Der Stellen-Scout durchsucht vielfältige Quellen und prüft Bewerbungswege.")
        task.output_json = json.dumps({"run_id": run_id})
        task.updated_at = utc_now()
        campaign.status = "researching"
        campaign.updated_at = utc_now()
        self.session.add_all([task, campaign])
        self.session.commit()

    def _launch_target_research(self, task: AgentTask) -> None:
        payload = json_object(task.input_json)
        target = self.session.get(ResearchTarget, payload.get("research_target_id"))
        campaign = self.session.get(Campaign, task.campaign_id)
        if target is None or campaign is None or target.campaign_id != campaign.id:
            raise ValueError("Targeted research requires a valid campaign target.")
        from backend.app.workflow.research_graph import observe_target_launch

        observe_target_launch(
            self.session,
            task=task,
            target=target,
            campaign=campaign,
        )
        if task.task_type == "job_research_target":
            from backend.app.agents.job_research_runtime import JobResearchRuntime, prepare_job_research_run

            run_id = prepare_job_research_run(
                campaign=campaign,
                research_target=target,
                session=self.session,
                settings=self.settings,
                candidate_goal=int(payload["candidate_goal"]) if payload.get("candidate_goal") else None,
                time_budget_seconds=int(payload["time_budget_seconds"]) if payload.get("time_budget_seconds") else None,
            )
            JobResearchRuntime(settings=self.settings).launch(run_id)
        else:
            from backend.app.agents.company_research_runtime import CompanyResearchRuntime
            from backend.app.api.routes import prepare_company_research_campaign
            from backend.app.schemas.api import CompanyResearchCampaignRequest

            brief = json_object(campaign.brief_json)
            time_budget_seconds = int(payload["time_budget_seconds"]) if payload.get("time_budget_seconds") else None
            prepared = prepare_company_research_campaign(
                CompanyResearchCampaignRequest(
                    run_id=f"campaign-{campaign.campaign_id}-{target.target_id}-{uuid4().hex[:8]}",
                    role_focus=str(brief.get("role_focus") or "Profile-aligned roles"),
                    locations=[target.label],
                    time_budget_minutes=(
                        max(1, (time_budget_seconds + 59) // 60)
                        if time_budget_seconds
                        else int(brief.get("time_budget_minutes") or 30)
                    ),
                    time_budget_seconds=time_budget_seconds,
                    max_companies=int(payload["candidate_goal"]) if payload.get("candidate_goal") else int(brief.get("max_companies") or 30),
                    notes=str(brief.get("notes")) if brief.get("notes") else None,
                    additional_guidance=str(brief.get("additional_guidance") or brief.get("company_preferences") or ""),
                    target_id=target.target_id,
                    target_kind=target.target_kind,
                    required_search_attempts=target.required_attempts,
                ),
                session=self.session,
                settings=self.settings,
            )
            run_id = prepared.run_id
            CompanyResearchRuntime(settings=self.settings).launch(run_id)
        target.status = "searching"
        target.run_id = run_id
        target.updated_at = utc_now()
        task.run_id = run_id
        task.progress = 15
        task.narrative = self._text(task.workspace_id, f"Searching {target.label} in an isolated coverage pass.", f"{target.label} wird in einem eigenen Abdeckungslauf durchsucht.")
        task.output_json = json.dumps({"run_id": run_id, "research_target_id": target.id}, sort_keys=True)
        task.updated_at = utc_now()
        self.session.add_all([target, task])
        self.session.commit()

    def _launch_job_verification(self, task: AgentTask) -> None:
        from backend.app.agents.job_verification_runtime import JobVerificationRuntime, prepare_job_verification_run

        campaign = self.session.get(Campaign, task.campaign_id)
        if campaign is None or campaign.campaign_type != "listed_job_search":
            raise ValueError("Job verification requires a listed-job campaign.")
        payload = json_object(task.input_json)
        job = self.session.exec(select(JobPosting).where(JobPosting.job_id == payload.get("job_id"))).first()
        if job is None:
            raise ValueError("The vacancy selected for verification no longer exists.")
        run_id = prepare_job_verification_run(campaign=campaign, job=job, session=self.session, settings=self.settings)
        JobVerificationRuntime(settings=self.settings).launch(run_id)
        task.run_id = run_id
        task.progress = 15
        task.narrative = self._text(task.workspace_id, f"The vacancy verifier is checking only {job.title} and its supplied application route.", f"Der Stellenprüfer prüft ausschließlich {job.title} und den angegebenen Bewerbungsweg.")
        task.output_json = json.dumps({"run_id": run_id, "job_id": job.job_id})
        task.updated_at = utc_now()
        self.session.add(task)
        self.session.commit()

    def _launch_application_draft(self, task: AgentTask) -> None:
        from backend.app.agents.application_draft_runtime import ApplicationDraftRuntime
        from backend.app.api.routes import _prepare_application_draft_response
        from backend.app.schemas.api import ApplicationDraftRequest

        company = self.session.get(Company, task.company_id)
        if company is None:
            raise ValueError("Company no longer exists.")
        campaign = self.session.get(Campaign, task.campaign_id)
        campaign_brief = json_object(campaign.brief_json) if campaign is not None else {}
        prepared = _prepare_application_draft_response(
            ApplicationDraftRequest(
                company_id=company.company_id,
                language=str(campaign_brief.get("application_language") or "auto"),
            ),
            session=self.session,
            settings=self.settings,
        )
        ApplicationDraftRuntime(settings=self.settings).launch(prepared.run_id)
        task.run_id = prepared.run_id
        task.progress = 20
        task.narrative = self._text(task.workspace_id, f"The CV and writing specialists are preparing {company.name}.", f"Die CV- und Textspezialisten bereiten die Unterlagen für {company.name} vor.")
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
        task.narrative = self._text(task.workspace_id, f"The CV and writing specialists are tailoring the application to {job.title}.", f"Die CV- und Textspezialisten passen die Bewerbung an {job.title} an.")
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
        task.narrative = self._text(task.workspace_id, f"The research specialist is looking for a suitable public contact at {company.name}.", f"Der Recherche-Spezialist sucht einen geeigneten öffentlichen Kontakt bei {company.name}.")
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
            self._complete(task, self._text(task.workspace_id, "Application is ready; this campaign stops at drafts.", "Die Bewerbung ist bereit; diese Kampagne endet bei den Entwürfen."))
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
        self._complete(task, self._text(task.workspace_id, f"Outreach to {company.name} passed the gate and was sent.", f"Die Kontaktaufnahme mit {company.name} hat die Prüfung bestanden und wurde gesendet."))

    def _reconcile_research(self, task: AgentTask, status: dict[str, Any]) -> None:
        state = str(status.get("status") or "running")
        counts = status.get("artifact_counts") or {}
        task.progress = min(90, max(task.progress, int(counts.get("companies", 0)) * 2))
        task.narrative = self._text(task.workspace_id, f"Research found {int(counts.get('companies', 0))} companies and is checking fit.", f"Die Recherche hat {int(counts.get('companies', 0))} Unternehmen gefunden und prüft die Passung.")
        task.updated_at = utc_now()
        self.session.add(task)
        campaign = self.session.get(Campaign, task.campaign_id)
        if campaign is None:
            raise ValueError("Campaign no longer exists.")
        file_ids = self.session.exec(select(ImportedFile.id).where(ImportedFile.run_id == task.run_id)).all()
        companies = self.session.exec(select(Company).where(Company.imported_file_id.in_(file_ids))).all() if file_ids else []
        for company in companies:
            if self._campaign_company(campaign.id, company.id) is None:
                self.session.add(
                    CampaignCompany(
                        campaign_id=campaign.id,
                        company_id=company.id,
                        stage="discovered",
                        stage_reason="Schema-valid research imported while discovery continues.",
                    )
                )
        if state not in TERMINAL_RUNTIME_STATUSES:
            self.session.commit()
            return
        if state in FAILED_RUNTIME_STATUSES:
            raise ValueError(f"Company research ended with {state}.")
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
            elif link.stage == "discovered" and link.stage_reason == "Schema-valid research imported while discovery continues.":
                conflicts = json.loads(company.policy_conflicts_json or "[]")
                link.stage = "archived" if conflicts else "qualified"
                link.disposition = "policy_excluded" if conflicts else None
                link.stage_reason = "Excluded by campaign policy." if conflicts else "Research and fit evidence imported."
                link.updated_at = utc_now()
                self.session.add(link)
            if link.stage != "archived":
                contact = self._latest_contact(company.id)
                if contact is None:
                    self.enqueue(
                        campaign=campaign,
                        company=company,
                        task_type="contact_research",
                        agent_role="contact_researcher",
                        narrative=self._text(campaign.workspace_id, f"Finding a suitable public recruiting contact for {company.name}.", f"Ein geeigneter öffentlicher Recruiting-Kontakt bei {company.name} wird gesucht."),
                    )
                else:
                    self._enqueue_application_draft(campaign, company)
        campaign.status = "preparing"
        campaign.updated_at = utc_now()
        self.session.add(campaign)
        self._complete(task, self._text(task.workspace_id, f"Research completed with {len(companies)} companies ready for the next specialist.", f"Die Recherche ist abgeschlossen; {len(companies)} Unternehmen sind für den nächsten Spezialisten bereit."))

    def _sync_target_attempts(self, campaign: Campaign, target: ResearchTarget, run_id: str) -> int:
        path = scoped_runs_root(self.settings.runs_root) / run_id / "logs" / "search_attempts.jsonl"
        if not path.is_file():
            return target.completed_attempts
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            attempt_key = str(item.get("attempt_key") or "").strip()
            if not attempt_key:
                continue
            existing = self.session.exec(
                select(ResearchSearchAttempt).where(
                    ResearchSearchAttempt.target_id == target.id,
                    ResearchSearchAttempt.attempt_key == attempt_key,
                )
            ).first()
            if existing is not None:
                continue
            self.session.add(
                ResearchSearchAttempt(
                    campaign_id=campaign.id,
                    target_id=target.id,
                    attempt_key=attempt_key,
                    source_category=str(item.get("source_category") or "general_web"),
                    query=str(item.get("query") or ""),
                    outcome=str(item.get("outcome") or "completed"),
                    result_count=max(0, int(item.get("result_count") or 0)),
                    metadata_json=json.dumps(item.get("metadata") or {}, sort_keys=True),
                    workspace_id=campaign.workspace_id,
                )
            )
        self.session.flush()
        target.completed_attempts = len(
            self.session.exec(select(ResearchSearchAttempt).where(ResearchSearchAttempt.target_id == target.id)).all()
        )
        return target.completed_attempts

    def _record_target_discoveries(self, campaign: Campaign, target: ResearchTarget, run_id: str, *, jobs: bool) -> int:
        file_ids = self.session.exec(select(ImportedFile.id).where(ImportedFile.run_id == run_id)).all()
        candidates: list[Any]
        if jobs:
            candidates = self.session.exec(select(JobPosting).where(JobPosting.imported_file_id.in_(file_ids))).all() if file_ids else []
        else:
            candidates = self.session.exec(select(Company).where(Company.imported_file_id.in_(file_ids))).all() if file_ids else []
        kind = "job" if jobs else "company"
        for candidate in candidates:
            external_id = candidate.job_id if jobs else candidate.company_id
            existing = self.session.exec(
                select(ResearchDiscovery).where(
                    ResearchDiscovery.target_id == target.id,
                    ResearchDiscovery.candidate_kind == kind,
                    ResearchDiscovery.candidate_external_id == external_id,
                )
            ).first()
            if existing is None:
                self.session.add(
                    ResearchDiscovery(
                        campaign_id=campaign.id,
                        target_id=target.id,
                        candidate_kind=kind,
                        candidate_external_id=external_id,
                        run_id=run_id,
                        workspace_id=campaign.workspace_id,
                    )
                )
        self.session.flush()
        target.candidate_count = self._assess_target_discoveries(
            target,
            candidate_kind=kind,
        )
        return target.candidate_count

    def _assess_target_discoveries(self, target: ResearchTarget, *, candidate_kind: str) -> int:
        discoveries = self.session.exec(
            select(ResearchDiscovery).where(
                ResearchDiscovery.target_id == target.id,
                ResearchDiscovery.candidate_kind == candidate_kind,
            )
        ).all()
        if not discoveries:
            return 0
        plan = self.session.get(ResearchPlan, target.research_plan_id)
        raw_plan = json_object(plan.raw_json) if plan is not None else {}
        external_ids = {item.candidate_external_id for item in discoveries}
        if candidate_kind == "job":
            candidates = {
                item.job_id: item
                for item in self.session.exec(
                    select(JobPosting).where(JobPosting.job_id.in_(external_ids))
                ).all()
            }
        else:
            candidates = {
                item.company_id: item
                for item in self.session.exec(
                    select(Company).where(Company.company_id.in_(external_ids))
                ).all()
            }
        match_count = 0
        for discovery in discoveries:
            candidate = candidates.get(discovery.candidate_external_id)
            if candidate is None:
                discovery.scope_status = "needs_review"
                reasons = ["candidate_record_missing"]
            elif candidate_kind == "job":
                discovery.scope_status, reasons = self._job_target_scope_status(
                    target,
                    candidate,
                    raw_plan,
                )
            else:
                discovery.scope_status, reasons = self._company_target_scope_status(
                    target,
                    candidate,
                )
            discovery.reason_codes_json = json.dumps(reasons, sort_keys=True)
            if discovery.scope_status == "match":
                match_count += 1
            self.session.add(discovery)
        return match_count

    @staticmethod
    def _target_coverage_complete(target: ResearchTarget, attempts: int) -> bool:
        return (
            attempts >= target.required_attempts
            and target.candidate_count >= target.guaranteed_candidate_goal
        )

    def _reconcile_target_research(self, task: AgentTask, status: dict[str, Any]) -> None:
        payload = json_object(task.input_json)
        target = self.session.get(ResearchTarget, payload.get("research_target_id"))
        campaign = self.session.get(Campaign, task.campaign_id)
        if target is None or campaign is None:
            raise ValueError("Research target no longer exists.")
        state = str(status.get("status") or "running")
        attempts = self._sync_target_attempts(campaign, target, task.run_id or "")
        count = self._record_target_discoveries(
            campaign,
            target,
            task.run_id or "",
            jobs=task.task_type == "job_research_target",
        )
        task.progress = min(90, max(task.progress, 20 + attempts * 15))
        task.narrative = self._text(
            task.workspace_id,
            f"{target.label}: {attempts}/{target.required_attempts} search attempts, {count} confirmed matches.",
            f"{target.label}: {attempts}/{target.required_attempts} Suchversuche, {count} bestÃ¤tigte Treffer.",
        )
        task.updated_at = utc_now()
        target.updated_at = utc_now()
        self.session.add_all([task, target])
        if state not in TERMINAL_RUNTIME_STATUSES:
            self.session.commit()
            return
        if state in FAILED_RUNTIME_STATUSES:
            if payload.get("budget_phase") == "shared":
                target.status = (
                    "covered"
                    if self._target_coverage_complete(target, attempts)
                    else "exhausted"
                )
                target.last_error = f"Shared-budget follow-up ended with {state}; confirmed coverage is preserved."
            else:
                target.status = "failed"
                target.last_error = f"Research runtime ended with {state}."
        elif self._target_coverage_complete(target, attempts):
            target.status = "covered"
            target.last_error = None
        else:
            target.status = "exhausted"
            if attempts < target.required_attempts:
                target.last_error = f"Only {attempts} of {target.required_attempts} required attempts were recorded."
            else:
                target.last_error = (
                    f"Only {target.candidate_count} of {target.guaranteed_candidate_goal} "
                    "confirmed target matches were found."
                )
        task.status = "completed"
        task.progress = 100
        task.completed_at = utc_now()
        task.locked_at = None
        task.locked_by = None
        task.narrative = self._text(
            task.workspace_id,
            f"{target.label} finished with {count} confirmed matches ({target.status}).",
            f"{target.label} wurde mit {count} bestÃ¤tigten Treffern abgeschlossen ({target.status}).",
        )
        runtime_state = status.get("state") if isinstance(status.get("state"), dict) else {}
        elapsed_seconds = runtime_state.get("elapsed_seconds")
        if isinstance(elapsed_seconds, int | float) and elapsed_seconds > 0:
            target.consumed_time_seconds += max(1, int(round(elapsed_seconds)))
        target.reserved_time_seconds = 0
        self.session.add_all([target, task])
        self.session.flush()
        from backend.app.workflow.research_graph import observe_target_reconciled

        observe_target_reconciled(
            self.session,
            task=task,
            target=target,
            campaign=campaign,
        )
        if not self._maybe_schedule_shared_research(campaign):
            self._maybe_finalize_balanced_campaign(campaign)
        self.session.commit()

    def _maybe_schedule_shared_research(self, campaign: Campaign) -> bool:
        plan = self.session.exec(
            select(ResearchPlan)
            .where(ResearchPlan.campaign_id == campaign.id, ResearchPlan.status == "confirmed")
            .order_by(ResearchPlan.version.desc())
        ).first()
        if plan is None:
            return False
        raw_plan = json_object(plan.raw_json)
        if raw_plan.get("schema_version") != "1.1":
            return False
        targets = self.session.exec(
            select(ResearchTarget).where(ResearchTarget.research_plan_id == plan.id).order_by(ResearchTarget.id)
        ).all()
        active = self.session.exec(
            select(AgentTask).where(
                AgentTask.campaign_id == campaign.id,
                AgentTask.task_type.in_(["company_research_target", "job_research_target"]),
                AgentTask.status.in_(["queued", "retry", "running"]),
            )
        ).all()
        if active or any(target.status not in {"covered", "exhausted", "failed"} for target in targets):
            return bool(active)
        effort = raw_plan.get("effort") if isinstance(raw_plan.get("effort"), dict) else {}
        candidate_goal = int(effort.get("candidate_goal") or 0)
        total_time_seconds = int(effort.get("time_budget_seconds") or 0)
        target_ids = {target.id for target in targets}
        discoveries = self.session.exec(
            select(ResearchDiscovery).where(
                ResearchDiscovery.target_id.in_(target_ids),
                ResearchDiscovery.scope_status == "match",
            )
        ).all()
        unique_candidates = len(
            {(item.candidate_kind, item.candidate_external_id) for item in discoveries}
        )
        needs_coverage = [
            target
            for target in targets
            if target.status != "failed"
            and (
                target.completed_attempts < target.required_attempts
                or target.candidate_count < target.guaranteed_candidate_goal
            )
        ]
        if unique_candidates >= candidate_goal and not needs_coverage:
            return False
        available_seconds = total_time_seconds - sum(
            target.consumed_time_seconds + target.reserved_time_seconds for target in targets
        )
        if available_seconds < 60:
            return False
        eligible = [
            target
            for target in targets
            if target.status != "failed"
            and target.shared_lease_count < MAX_SHARED_LEASES_PER_TARGET
            and (target in needs_coverage or unique_candidates < candidate_goal)
        ]
        if not eligible:
            return False
        eligible.sort(
            key=lambda target: (
                0 if target in needs_coverage else 1,
                target.shared_lease_count,
                -target.candidate_count,
                target.id or 0,
            )
        )
        max_parallel = min(int(effort.get("max_parallel_targets") or 1), len(eligible))
        selected = eligible[:max_parallel]
        remaining_candidate_goal = max(candidate_goal - unique_candidates, 1)
        task_type = "job_research_target" if campaign.campaign_type == "listed_job_search" else "company_research_target"
        agent_role = "vacancy_scout" if campaign.campaign_type == "listed_job_search" else "company_researcher"
        locale = workspace_locale(self.session, campaign.workspace_id)
        scheduled = 0
        for target in selected:
            if available_seconds < 60:
                break
            lease_seconds = min(SHARED_RESEARCH_LEASE_SECONDS, available_seconds)
            lease_goal = min(SHARED_RESEARCH_LEASE_CANDIDATES, remaining_candidate_goal)
            target.status = "queued"
            target.reserved_time_seconds = lease_seconds
            target.shared_lease_count += 1
            target.updated_at = utc_now()
            self.session.add(target)
            shared_task = AgentTask(
                task_id=f"task-{uuid4()}",
                campaign_id=campaign.id,
                agent_role=agent_role,
                task_type=task_type,
                narrative=localized_text(
                        locale,
                        f"Queued a shared-budget follow-up pass for {target.label}.",
                        f"Ein Folgelauf aus dem gemeinsamen Budget für {target.label} wurde eingeplant.",
                    ),
                input_json=json.dumps(
                        {
                            "research_target_id": target.id,
                            "target_id": target.target_id,
                            "budget_phase": "shared",
                            "lease_generation": target.shared_lease_count,
                            "candidate_goal": lease_goal,
                            "time_budget_seconds": lease_seconds,
                        },
                        sort_keys=True,
                    ),
                workspace_id=campaign.workspace_id,
            )
            from backend.app.workflow.research_graph import correlate_target_task

            correlate_target_task(
                self.session,
                task=shared_task,
                target=target,
                campaign=campaign,
                logical_generation=target.shared_lease_count,
            )
            self.session.add(shared_task)
            available_seconds -= lease_seconds
            remaining_candidate_goal = max(remaining_candidate_goal - lease_goal, 1)
            scheduled += 1
        return scheduled > 0

    @staticmethod
    def _remote_scope_status(job: JobPosting) -> tuple[str, list[str]]:
        if job.work_mode == "fully_remote":
            regions = {str(item).casefold() for item in json.loads(job.remote_regions_json or "[]")}
            if regions and not any("europe" in item or item in {"eu", "eea", "worldwide", "global"} for item in regions):
                return "conflict", ["remote_region_conflict"]
            return "match", []
        if job.work_mode in {"hybrid", "onsite"}:
            return "conflict", ["remote_target_but_not_fully_remote"]
        value = (job.remote_policy or "").casefold()
        if any(token in value for token in ("hybrid", "partly remote", "teilweise remote", "onsite", "on-site")):
            return "conflict", ["remote_target_but_not_fully_remote"]
        if "remote" in value:
            if any(token in value for token in ("us only", "united states only", "north america only")):
                return "conflict", ["remote_region_conflict"]
            return "match", []
        return "needs_review", ["remote_policy_unconfirmed"]

    def _job_target_scope_status(
        self,
        target: ResearchTarget,
        job: JobPosting,
        raw_plan: dict[str, Any],
    ) -> tuple[str, list[str]]:
        if target.target_kind == "remote":
            status, reasons = self._remote_scope_status(job)
        else:
            normalized_locations = " | ".join(json.loads(job.locations_json or "[]")).casefold()
            target_value = target.normalized_value.casefold()
            status, reasons = (
                ("match", [])
                if target_value and target_value in normalized_locations
                else ("needs_review", ["geographic_match_unconfirmed"])
            )
        minimum_duration = next(
            (
                int(item["value"])
                for item in raw_plan.get("hard_constraints", [])
                if item.get("key") == "minimum_duration_weeks"
                and isinstance(item.get("value"), int)
            ),
            None,
        )
        if minimum_duration is not None:
            if job.duration_max_weeks is not None and job.duration_max_weeks < minimum_duration:
                return "conflict", ["duration_below_campaign_minimum"]
            if (
                job.duration_min_weeks is None
                and job.duration_max_weeks is None
                and status == "match"
            ):
                return "needs_review", ["duration_unconfirmed"]
        return status, reasons

    @staticmethod
    def _company_target_scope_status(
        target: ResearchTarget,
        company: Company,
    ) -> tuple[str, list[str]]:
        conflicts = json.loads(company.policy_conflicts_json or "[]")
        if conflicts:
            return "conflict", ["company_policy_conflict"]
        if target.target_kind == "remote":
            remote_policy = (company.remote_policy or "").casefold()
            if any(token in remote_policy for token in ("onsite only", "on-site only", "no remote")):
                return "conflict", ["remote_target_but_company_is_onsite_only"]
            if not any(token in remote_policy for token in ("remote", "distributed", "work from home")):
                return "needs_review", ["company_remote_policy_unconfirmed"]
            return "match", []
        locations = " | ".join(json.loads(company.locations_json or "[]")).casefold()
        if target.normalized_value.casefold() not in locations:
            return "needs_review", ["company_geographic_match_unconfirmed"]
        return "match", []

    def _maybe_finalize_balanced_campaign(self, campaign: Campaign) -> None:
        plan = self.session.exec(
            select(ResearchPlan)
            .where(ResearchPlan.campaign_id == campaign.id, ResearchPlan.status == "confirmed")
            .order_by(ResearchPlan.version.desc())
        ).first()
        if plan is None:
            return
        targets = self.session.exec(select(ResearchTarget).where(ResearchTarget.research_plan_id == plan.id)).all()
        if not targets or any(target.status not in {"covered", "exhausted", "failed"} for target in targets):
            return
        raw_plan = json_object(plan.raw_json)
        brief = json_object(campaign.brief_json)
        discoveries = self.session.exec(select(ResearchDiscovery).where(ResearchDiscovery.campaign_id == campaign.id)).all()
        target_by_id = {target.id: target for target in targets}
        if campaign.campaign_type == "listed_job_search":
            jobs = {
                item.job_id: item
                for item in self.session.exec(
                    select(JobPosting).where(JobPosting.job_id.in_({item.candidate_external_id for item in discoveries if item.candidate_kind == "job"}))
                ).all()
            }
            assessed: dict[str, tuple[JobPosting, str, list[str]]] = {}
            for discovery in discoveries:
                job = jobs.get(discovery.candidate_external_id)
                target = target_by_id.get(discovery.target_id)
                if job is None or target is None or discovery.candidate_kind != "job":
                    continue
                status, reasons = self._job_target_scope_status(
                    target,
                    job,
                    raw_plan,
                )
                previous = assessed.get(job.job_id)
                if previous is None or {"match": 2, "needs_review": 1, "conflict": 0}[status] > {"match": 2, "needs_review": 1, "conflict": 0}[previous[1]]:
                    assessed[job.job_id] = (job, status, reasons)
                discovery.scope_status = status
                discovery.reason_codes_json = json.dumps(reasons, sort_keys=True)
                self.session.add(discovery)
            ranked: list[tuple[JobPosting, str, float, float]] = []
            for job, scope_status, reasons in assessed.values():
                if scope_status == "conflict":
                    self.session.add(AuditLog(actor_type="backend", action="research_candidate_excluded", entity_type="job_posting", entity_id=job.job_id, result_status="excluded", reason_codes_json=json.dumps(reasons), metadata_json=json.dumps({"campaign_id": campaign.campaign_id})))
                    continue
                fit = self.session.exec(
                    select(JobFitEvaluation).where(JobFitEvaluation.job_posting_id == job.id).order_by(JobFitEvaluation.created_at.desc())
                ).first()
                ranked.append((job, scope_status, fit.role_fit_score if fit else 0.0, fit.company_fit_score if fit else 0.0))
            ranked.sort(
                key=lambda item: (
                    0 if item[1] == "match" else 1,
                    0 if item[0].vacancy_status == "verified_open" else 1,
                    -item[2],
                    -item[3],
                    -(item[0].date_posted.timestamp() if item[0].date_posted else 0),
                    -item[0].confidence,
                    item[0].job_id,
                )
            )
            retained = ranked[: int(brief.get("max_jobs") or 30)]
            retained_ids = {job.job_id for job, *_ in retained}
            for job, scope_status, *_ in retained:
                link = self.session.exec(
                    select(CampaignJob).where(CampaignJob.campaign_id == campaign.id, CampaignJob.job_posting_id == job.id)
                ).first()
                if link is None:
                    self.session.add(CampaignJob(campaign_id=campaign.id, job_posting_id=job.id, application_status="discovered", status_note="Location scope needs review." if scope_status == "needs_review" else None, workspace_id=campaign.workspace_id))
            for target in targets:
                target.retained_count = len(
                    {
                        item.candidate_external_id
                        for item in discoveries
                        if item.target_id == target.id
                        and item.scope_status == "match"
                        and item.candidate_external_id in retained_ids
                    }
                )
                self.session.add(target)
        else:
            companies = {
                item.company_id: item
                for item in self.session.exec(
                    select(Company).where(Company.company_id.in_({item.candidate_external_id for item in discoveries if item.candidate_kind == "company"}))
                ).all()
            }
            assessed_companies: dict[str, tuple[Company, str, list[str]]] = {}
            for discovery in discoveries:
                company = companies.get(discovery.candidate_external_id)
                target = target_by_id.get(discovery.target_id)
                if company is None or target is None or discovery.candidate_kind != "company":
                    continue
                status, reasons = self._company_target_scope_status(
                    target,
                    company,
                )
                previous = assessed_companies.get(company.company_id)
                if previous is None or {"match": 2, "needs_review": 1, "conflict": 0}[status] > {
                    "match": 2,
                    "needs_review": 1,
                    "conflict": 0,
                }[previous[1]]:
                    assessed_companies[company.company_id] = (company, status, reasons)
                discovery.scope_status = status
                discovery.reason_codes_json = json.dumps(reasons, sort_keys=True)
                self.session.add(discovery)
            ordered = sorted(
                (item for item in assessed_companies.values() if item[1] != "conflict"),
                key=lambda item: (
                    0 if item[1] == "match" else 1,
                    -item[0].confidence,
                    item[0].normalized_name,
                    item[0].company_id,
                ),
            )
            retained = ordered[: int(brief.get("max_companies") or 30)]
            retained_ids = {item.company_id for item, *_ in retained}
            for company, scope_status, _ in retained:
                if self._campaign_company(campaign.id, company.id) is None:
                    self.session.add(
                        CampaignCompany(
                            campaign_id=campaign.id,
                            company_id=company.id,
                            stage="qualified",
                            stage_reason=(
                                "Retained after balanced target coverage; location or remote scope needs review."
                                if scope_status == "needs_review"
                                else "Retained after balanced target coverage."
                            ),
                            workspace_id=campaign.workspace_id,
                        )
                    )
                next_task_type = "application_draft" if self._latest_contact(company.id) is not None else "contact_research"
                existing_task = self.session.exec(
                    select(AgentTask).where(
                        AgentTask.campaign_id == campaign.id,
                        AgentTask.company_id == company.id,
                        AgentTask.task_type == next_task_type,
                        AgentTask.status.in_(["queued", "retry", "running", "completed"]),
                    )
                ).first()
                if existing_task is None:
                    self.session.add(
                        AgentTask(
                            task_id=f"task-{uuid4()}",
                            campaign_id=campaign.id,
                            company_id=company.id,
                            agent_role=(
                                "resume_and_email_team"
                                if next_task_type == "application_draft"
                                else "contact_researcher"
                            ),
                            task_type=next_task_type,
                            narrative=self._text(
                                campaign.workspace_id,
                                f"Preparing a tailored application for {company.name}."
                                if next_task_type == "application_draft"
                                else f"Finding a suitable public recruiting contact for {company.name}.",
                                f"Eine individuelle Bewerbung für {company.name} wird vorbereitet."
                                if next_task_type == "application_draft"
                                else f"Ein geeigneter öffentlicher Recruiting-Kontakt bei {company.name} wird gesucht.",
                            ),
                            workspace_id=campaign.workspace_id,
                        )
                    )
            for target in targets:
                target.retained_count = len(
                    {
                        item.candidate_external_id
                        for item in discoveries
                        if item.target_id == target.id
                        and item.scope_status == "match"
                        and item.candidate_external_id in retained_ids
                    }
                )
                self.session.add(target)
        plan.status = "completed"
        plan.updated_at = utc_now()
        campaign.status = "preparing" if campaign.campaign_type == "initiative_outreach" and retained else "active"
        campaign.updated_at = utc_now()
        self.session.add_all([plan, campaign])
        self.session.flush()
        from backend.app.workflow.research_graph import observe_campaign_finalized

        observe_campaign_finalized(
            self.session,
            campaign=campaign,
            plan=plan,
            targets=targets,
        )

    def _reconcile_job_research(self, task: AgentTask, status: dict[str, Any]) -> None:
        state = str(status.get("status") or "running")
        counts = status.get("artifact_counts") or {}
        task.progress = min(90, max(task.progress, int(counts.get("jobs", 0)) * 3))
        task.narrative = self._text(task.workspace_id, f"Vacancy research found {int(counts.get('jobs', 0))} listings and is checking validity and fit.", f"Die Stellenrecherche hat {int(counts.get('jobs', 0))} Ausschreibungen gefunden und prüft Gültigkeit und Passung.")
        task.updated_at = utc_now()
        self.session.add(task)
        campaign = self.session.get(Campaign, task.campaign_id)
        if campaign is None:
            raise ValueError("Campaign no longer exists.")
        file_ids = self.session.exec(select(ImportedFile.id).where(ImportedFile.run_id == task.run_id)).all()
        jobs = self.session.exec(select(JobPosting).where(JobPosting.imported_file_id.in_(file_ids))).all() if file_ids else []
        for job in jobs:
            existing_link = self.session.exec(
                select(CampaignJob).where(
                    CampaignJob.campaign_id == campaign.id,
                    CampaignJob.job_posting_id == job.id,
                )
            ).first()
            if existing_link is None:
                self.session.add(CampaignJob(campaign_id=campaign.id, job_posting_id=job.id, application_status="discovered"))
        if state not in TERMINAL_RUNTIME_STATUSES:
            self.session.commit()
            return
        if state in FAILED_RUNTIME_STATUSES:
            raise ValueError(f"Job research ended with {state}.")
        for job in jobs:
            link = self.session.exec(select(CampaignJob).where(CampaignJob.campaign_id == campaign.id, CampaignJob.job_posting_id == job.id)).first()
            if link is None:
                self.session.add(CampaignJob(campaign_id=campaign.id, job_posting_id=job.id, application_status="discovered"))
        campaign.status = "active"
        campaign.updated_at = utc_now()
        self.session.add(campaign)
        self._complete(task, self._text(task.workspace_id, f"Vacancy research completed with {len(jobs)} listings retained with verification evidence.", f"Die Stellenrecherche ist abgeschlossen; {len(jobs)} Ausschreibungen wurden mit Prüfbelegen übernommen."))

    def _reconcile_job_verification(self, task: AgentTask, status: dict[str, Any]) -> None:
        state = str(status.get("status") or "running")
        task.progress = 70 if state not in TERMINAL_RUNTIME_STATUSES else task.progress
        task.narrative = self._text(task.workspace_id, "The vacancy verifier is checking the selected listing and application route; no discovery is running.", "Der Stellenprüfer kontrolliert die ausgewählte Ausschreibung und den Bewerbungsweg; es läuft keine weitere Suche.")
        task.updated_at = utc_now()
        self.session.add(task)
        if state not in TERMINAL_RUNTIME_STATUSES:
            self.session.commit()
            return
        if state in FAILED_RUNTIME_STATUSES:
            raise ValueError(f"Job verification ended with {state}.")
        payload = json_object(task.input_json)
        file_ids = self.session.exec(select(ImportedFile.id).where(ImportedFile.run_id == task.run_id)).all()
        jobs = self.session.exec(select(JobPosting).where(JobPosting.imported_file_id.in_(file_ids))).all() if file_ids else []
        if len(jobs) != 1 or jobs[0].job_id != payload.get("job_id"):
            raise ValueError("Vacancy verification completed without updating exactly the selected vacancy.")
        self._complete(task, self._text(task.workspace_id, "The selected vacancy was verified from its current source evidence; no other jobs were searched or imported.", "Die ausgewählte Stelle wurde anhand der aktuellen Quellenbelege geprüft; weitere Stellen wurden weder gesucht noch importiert."))

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
        self._complete(task, self._text(task.workspace_id, f"A suitable public contact for {company.name} was imported; application preparation is queued.", f"Ein geeigneter öffentlicher Kontakt für {company.name} wurde importiert; die Bewerbungsvorbereitung ist eingeplant."))

    def _enqueue_application_draft(self, campaign: Campaign, company: Company) -> AgentTask:
        return self.enqueue(
            campaign=campaign,
            company=company,
            task_type="application_draft",
            agent_role="resume_and_email_team",
            narrative=self._text(campaign.workspace_id, f"Preparing a tailored application for {company.name}.", f"Eine individuelle Bewerbung für {company.name} wird vorbereitet."),
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
        task.last_error = self._text(task.workspace_id, f"No suitable public professional contact was found for {company.name}.", f"Für {company.name} wurde kein geeigneter öffentlicher beruflicher Kontakt gefunden.")
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
                title=self._text(task.workspace_id, f"No suitable contact found for {company.name}", f"Kein geeigneter Kontakt für {company.name} gefunden"),
                explanation=self._text(
                    task.workspace_id,
                    f"Contact research completed for {company.name}, but no schema-valid, sourced public professional email address was imported. Application drafting has not been started.",
                    f"Die Kontaktrecherche für {company.name} ist abgeschlossen, aber es wurde keine schema-gültige, belegte öffentliche berufliche E-Mail-Adresse importiert. Die Bewerbungserstellung wurde nicht gestartet.",
                ),
                recommended_action=self._text(task.workspace_id, "Retry contact research with new guidance or skip this company.", "Starte die Kontaktrecherche mit neuen Hinweisen erneut oder überspringe dieses Unternehmen."),
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
                narrative=self._text(campaign.workspace_id, f"Running final deterministic checks for {company.name}.", f"Die abschließenden deterministischen Prüfungen für {company.name} laufen."),
            )
        self._complete(task, self._text(task.workspace_id, f"The tailored CV and email for {company.name} are ready.", f"Der angepasste Lebenslauf und die E-Mail für {company.name} sind bereit."))

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
        self._index_documents(task, company, job_id=job.job_id, job_title=job.title)
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
        self._complete(task, self._text(task.workspace_id, f"The vacancy-tailored CV and cover letter for {job.title} are ready.", f"Der auf die Stelle zugeschnittene Lebenslauf und das Anschreiben für {job.title} sind bereit."))

    def _index_documents(self, task: AgentTask, company: Company, *, job_id: str | None = None, job_title: str | None = None) -> None:
        if not task.run_id:
            return
        output = scoped_runs_root(self.settings.runs_root) / task.run_id / "output"
        if not output.is_dir():
            return
        indexed_kinds = {
            kind
            for kind in self.session.exec(
                select(Document.document_type).where(
                    Document.run_id == task.run_id,
                    Document.mime_type == "application/pdf",
                )
            ).all()
        }
        for path in sorted(output.rglob("*")):
            if not path.is_file() or path.suffix.lower() != ".pdf":
                continue
            normalized_name = path.name.casefold()
            is_cover_letter = any(token in normalized_name for token in ("anschreiben", "cover-letter", "cover_letter"))
            is_cv = any(token in normalized_name for token in ("lebenslauf", "resume", "-cv", "_cv"))
            kind = "cover_letter" if is_cover_letter else "tailored_cv" if is_cv else None
            if kind is None or kind in indexed_kinds:
                continue
            relative = path.relative_to(scoped_runs_root(self.settings.runs_root)).as_posix()
            data = path.read_bytes()
            title_kind = "Tailored CV" if kind == "tailored_cv" else "Cover letter"
            self.session.add(
                Document(
                    document_id=f"document-{uuid4()}",
                    campaign_id=task.campaign_id,
                    company_id=company.id,
                    run_id=task.run_id,
                    document_type=kind,
                    title=f"{company.name} — {title_kind}",
                    filename=path.name,
                    relative_path=relative,
                    mime_type="application/pdf",
                    size_bytes=len(data),
                    content_hash=hashlib.sha256(data).hexdigest(),
                    provenance_json=json.dumps({"agent_task_id": task.task_id, "run_id": task.run_id, "job_id": job_id, "job_title": job_title}),
                )
            )
            indexed_kinds.add(kind)

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
            task.narrative = self._text(task.workspace_id, "A specialist hit a problem and will retry automatically.", "Bei einem Spezialisten ist ein Problem aufgetreten; der Versuch wird automatisch wiederholt.")
        else:
            task.status = "blocked"
            task.narrative = self._text(task.workspace_id, "The specialist could not resolve this without your help.", "Der Spezialist konnte das Problem nicht ohne deine Hilfe lösen.")
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
        self.worker_id = f"workflow-worker-{uuid4()}"
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
        action: str | None = None
        with Session(db_session_module.engine) as session:
            now = utc_now()
            expired_before = now - timedelta(seconds=WORKFLOW_TASK_LEASE_SECONDS)
            running = session.exec(
                select(AgentTask).where(
                    AgentTask.status == "running",
                    AgentTask.task_type.in_([
                        "company_research",
                        "company_research_target",
                        "job_research",
                        "job_research_target",
                        "job_verification",
                        "contact_research",
                        "application_draft",
                        "job_application_draft",
                    ]),
                ).order_by(AgentTask.updated_at)
            ).all()
            target_task_types = {"company_research_target", "job_research_target"}
            running_target_count = sum(1 for item in running if item.task_type in target_task_types)
            queued_target = session.exec(
                select(AgentTask).where(
                    AgentTask.status.in_(["queued", "retry"]),
                    AgentTask.available_at <= utc_now(),
                    AgentTask.task_type.in_(list(target_task_types)),
                ).order_by(AgentTask.available_at, AgentTask.created_at)
            ).first()
            can_launch_target = (
                queued_target is not None
                and running_target_count < self.settings.research_target_max_concurrency
                and all(item.task_type in target_task_types for item in running)
            )
            if can_launch_target:
                task = queued_target
            else:
                task = session.exec(
                    select(AgentTask).where(
                        AgentTask.status == "running",
                        AgentTask.task_type.in_([
                            "company_research",
                            "company_research_target",
                            "job_research",
                            "job_research_target",
                            "job_verification",
                            "contact_research",
                            "application_draft",
                            "job_application_draft",
                        ]),
                        or_(
                            AgentTask.locked_by == self.worker_id,
                            AgentTask.locked_at.is_(None),
                            AgentTask.locked_at <= expired_before,
                        ),
                    ).order_by(AgentTask.updated_at)
                ).first()
                if task is None and running:
                    return False
                if task is None:
                    task = session.exec(
                        select(AgentTask).where(
                            AgentTask.status.in_(["queued", "retry"]),
                            AgentTask.available_at <= now,
                        ).order_by(AgentTask.available_at, AgentTask.created_at)
                    ).first()
            if task is None or task.workspace_id is None:
                return False
            if task.status in {"queued", "retry"}:
                result = session.exec(
                    update(AgentTask)
                    .where(
                        AgentTask.id == task.id,
                        AgentTask.status.in_(["queued", "retry"]),
                        AgentTask.available_at <= now,
                    )
                    .values(
                        status="running",
                        started_at=task.started_at or now,
                        locked_at=now,
                        locked_by=self.worker_id,
                        attempt_count=AgentTask.attempt_count + 1,
                        progress=max(task.progress, 5),
                        updated_at=now,
                    )
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount != 1:
                    session.rollback()
                    return False
                action = "launch"
            else:
                result = session.exec(
                    update(AgentTask)
                    .where(
                        AgentTask.id == task.id,
                        AgentTask.status == "running",
                        or_(
                            AgentTask.locked_by == self.worker_id,
                            AgentTask.locked_at.is_(None),
                            AgentTask.locked_at <= expired_before,
                        ),
                    )
                    .values(
                        locked_at=now,
                        locked_by=self.worker_id,
                        updated_at=now,
                    )
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount != 1:
                    session.rollback()
                    return False
                action = "reconcile"
            session.commit()
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
            if action == "reconcile":
                if not scoped_task.run_id:
                    engine.block_uncertain_external_launch(scoped_task)
                    return True
                engine.reconcile(scoped_task)
                if scoped_task.status == "running" and scoped_task.locked_by == self.worker_id:
                    scoped_task.locked_at = utc_now()
                    scoped_task.updated_at = utc_now()
                    scoped_session.add(scoped_task)
                    scoped_session.commit()
            else:
                engine.process(scoped_task, already_claimed=True)
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
