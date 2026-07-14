from __future__ import annotations

import json
import re
from html import escape
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, col, select

from backend.app.auth.context import current_identity, scoped_runs_root
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import (
    AuditLog,
    AgentTask,
    Campaign,
    CampaignCompany,
    CampaignJob,
    Company,
    Contact,
    Document,
    EmailDraft,
    FitEvaluation,
    GmailConnection,
    ImportedFile,
    MasterCvProfileSnapshot,
    JobApplicationPackage,
    JobFitEvaluation,
    JobPosting,
    JobSourceTrust,
    OutreachRecord,
    PolicySnapshot,
    ReviewException,
    SentMessage,
    UserProfileSnapshot,
    utc_now,
)
from backend.app.db.session import get_session
from backend.app.workflow.engine import WorkflowEngine


router = APIRouter(tags=["product"])


class CampaignCreate(BaseModel):
    campaign_type: Literal["initiative_outreach", "listed_job_search"] = "initiative_outreach"
    name: str = Field(min_length=1, max_length=160)
    role_focus: str = Field(default="Profile-aligned roles", min_length=1, max_length=240)
    locations: list[str] = Field(default_factory=list, max_length=20)
    company_preferences: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    time_budget_minutes: int = Field(default=30, ge=1, le=240)
    max_companies: int = Field(default=30, ge=1, le=100)
    max_jobs: int = Field(default=30, ge=1, le=100)
    freshness_days: int = Field(default=30, ge=1, le=180)
    seniority: list[str] = Field(default_factory=list, max_length=20)
    employment_types: list[str] = Field(default_factory=list, max_length=20)
    work_modes: list[str] = Field(default_factory=list, max_length=10)
    minimum_salary: int | None = Field(default=None, ge=0)
    languages: list[str] = Field(default_factory=list, max_length=20)
    sending_mode: Literal["prepare_only", "gated_autosend"] = "prepare_only"


class CampaignModeUpdate(BaseModel):
    sending_mode: Literal["prepare_only", "gated_autosend"]


class JobApplicationStatusUpdate(BaseModel):
    status: Literal["discovered", "saved", "preparing", "ready", "applied", "interview", "offer", "rejected", "withdrawn"]
    note: str | None = Field(default=None, max_length=2000)


class JobSourceTrustUpdate(BaseModel):
    domain: str = Field(min_length=1, max_length=255)
    trust_level: Literal["verification_capable", "discovery_only", "blocked"]
    enabled: bool = True


class ExceptionResolution(BaseModel):
    action: Literal["retry", "skip"]
    note: str | None = Field(default=None, max_length=2000)


def _approved(session: Session, model: type[Any]) -> Any | None:
    return session.exec(
        select(model)
        .where(model.status == "approved")
        .order_by(model.imported_file_id.is_(None), model.imported_at.desc())
    ).first()


def _campaign(session: Session, campaign_id: str) -> Campaign:
    campaign = session.exec(select(Campaign).where(Campaign.campaign_id == campaign_id)).first()
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found.")
    return campaign


def _campaign_response(campaign: Campaign, session: Session) -> dict[str, Any]:
    links = session.exec(select(CampaignCompany).where(CampaignCompany.campaign_id == campaign.id)).all()
    stages = Counter(item.stage for item in links)
    open_exceptions = session.exec(
        select(ReviewException).where(
            ReviewException.campaign_id == campaign.id,
            ReviewException.status == "open",
        )
    ).all()
    active_tasks = session.exec(
        select(AgentTask).where(
            AgentTask.campaign_id == campaign.id,
            AgentTask.status.in_(["queued", "retry", "running", "paused"]),
        )
    ).all()
    return {
        "id": campaign.campaign_id,
        "name": campaign.name,
        "campaign_type": campaign.campaign_type,
        "status": campaign.status,
        "sending_mode": campaign.sending_mode,
        "brief": json.loads(campaign.brief_json or "{}"),
        "stages": dict(stages),
        "company_count": len(links),
        "job_count": len(session.exec(select(CampaignJob).where(CampaignJob.campaign_id == campaign.id)).all()),
        "active_task_count": len(active_tasks),
        "exception_count": len(open_exceptions),
        "started_at": campaign.started_at,
        "created_at": campaign.created_at,
        "updated_at": campaign.updated_at,
    }


@router.post("/campaigns", status_code=201)
def create_campaign(
    payload: CampaignCreate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    identity = current_identity()
    if identity is None:
        raise HTTPException(status_code=409, detail="Campaigns require an authenticated workspace.")
    profile = _approved(session, UserProfileSnapshot)
    master_cv = _approved(session, MasterCvProfileSnapshot)
    policy = _approved(session, PolicySnapshot)
    if profile is None or master_cv is None or policy is None:
        raise HTTPException(status_code=409, detail="Approve your profile, master CV, and policy before starting a campaign.")
    if payload.sending_mode == "gated_autosend":
        if payload.campaign_type == "listed_job_search":
            raise HTTPException(status_code=422, detail="Job-listing campaigns never submit applications or send outreach.")
        gmail = session.exec(
            select(GmailConnection).where(
                GmailConnection.user_id == identity.user_id,
                GmailConnection.status == "connected",
            )
        ).first()
        if gmail is None:
            raise HTTPException(status_code=409, detail="Connect Gmail before choosing gated autosend.")
    campaign = Campaign(
        campaign_id=f"campaign-{uuid4()}",
        name=payload.name.strip(),
        campaign_type=payload.campaign_type,
        status="active",
        sending_mode=payload.sending_mode,
        brief_json=json.dumps(
            {
                "role_focus": payload.role_focus,
                "locations": payload.locations,
                "company_preferences": payload.company_preferences,
                "notes": payload.notes,
                "time_budget_minutes": payload.time_budget_minutes,
                "max_companies": payload.max_companies,
                "max_jobs": payload.max_jobs,
                "freshness_days": payload.freshness_days,
                "seniority": payload.seniority,
                "employment_types": payload.employment_types,
                "work_modes": payload.work_modes,
                "minimum_salary": payload.minimum_salary,
                "languages": payload.languages,
            },
            sort_keys=True,
        ),
        user_profile_snapshot_id=profile.id,
        master_cv_profile_snapshot_id=master_cv.id,
        policy_snapshot_id=policy.id,
        workspace_id=identity.effective_workspace_id,
        started_at=utc_now(),
    )
    session.add(campaign)
    session.commit()
    session.refresh(campaign)
    if campaign.campaign_type == "listed_job_search":
        WorkflowEngine(session).enqueue(
            campaign=campaign,
            task_type="job_research",
            agent_role="vacancy_scout",
            narrative="Your vacancy scout is ready to discover and verify open positions.",
        )
    else:
        WorkflowEngine(session).enqueue(
            campaign=campaign,
            task_type="company_research",
            agent_role="company_researcher",
            narrative="Your research specialist is ready to discover strong-fit companies.",
        )
    return _campaign_response(campaign, session)


@router.get("/campaigns")
def list_campaigns(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    campaigns = session.exec(select(Campaign).order_by(Campaign.updated_at.desc())).all()
    return [_campaign_response(item, session) for item in campaigns]


@router.get("/campaigns/{campaign_id}")
def get_campaign(campaign_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    return _campaign_response(_campaign(session, campaign_id), session)


@router.post("/campaigns/{campaign_id}/pause")
def pause_campaign(campaign_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    campaign = _campaign(session, campaign_id)
    campaign.status = "paused"
    campaign.paused_at = utc_now()
    campaign.updated_at = utc_now()
    tasks = session.exec(
        select(AgentTask).where(
            AgentTask.campaign_id == campaign.id,
            AgentTask.status.in_(["queued", "retry"]),
        )
    ).all()
    for task in tasks:
        task.status = "paused"
        task.updated_at = utc_now()
        session.add(task)
    session.add(campaign)
    session.commit()
    return _campaign_response(campaign, session)


@router.post("/campaigns/{campaign_id}/resume")
def resume_campaign(campaign_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    campaign = _campaign(session, campaign_id)
    campaign.status = "active"
    campaign.paused_at = None
    campaign.updated_at = utc_now()
    tasks = session.exec(
        select(AgentTask).where(AgentTask.campaign_id == campaign.id, AgentTask.status == "paused")
    ).all()
    for task in tasks:
        task.status = "queued"
        task.available_at = utc_now()
        task.updated_at = utc_now()
        session.add(task)
    session.add(campaign)
    session.commit()
    return _campaign_response(campaign, session)


@router.patch("/campaigns/{campaign_id}/sending-mode")
def update_campaign_mode(
    campaign_id: str,
    payload: CampaignModeUpdate,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    campaign = _campaign(session, campaign_id)
    if campaign.campaign_type == "listed_job_search" and payload.sending_mode != "prepare_only":
        raise HTTPException(status_code=422, detail="Job-listing campaigns are manual-submit only.")
    if payload.sending_mode == "gated_autosend":
        identity = current_identity()
        gmail = (
            session.exec(
                select(GmailConnection).where(
                    GmailConnection.user_id == identity.user_id,
                    GmailConnection.status == "connected",
                )
            ).first()
            if identity is not None
            else None
        )
        if gmail is None:
            raise HTTPException(status_code=409, detail="Connect Gmail before choosing gated autosend.")
    campaign.sending_mode = payload.sending_mode
    campaign.updated_at = utc_now()
    session.add(campaign)
    session.commit()
    return _campaign_response(campaign, session)


@router.get("/campaigns/{campaign_id}/pipeline")
def campaign_pipeline(campaign_id: str, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    campaign = _campaign(session, campaign_id)
    links = session.exec(
        select(CampaignCompany).where(CampaignCompany.campaign_id == campaign.id).order_by(CampaignCompany.updated_at.desc())
    ).all()
    result: list[dict[str, Any]] = []
    for link in links:
        company = session.get(Company, link.company_id)
        if company is None:
            continue
        fit = session.exec(
            select(FitEvaluation).where(FitEvaluation.company_id == company.id).order_by(FitEvaluation.created_at.desc())
        ).first()
        draft = session.exec(
            select(EmailDraft).where(EmailDraft.company_id == company.id).order_by(EmailDraft.created_at.desc())
        ).first()
        result.append(
            {
                "id": company.company_id,
                "name": company.name,
                "domain": company.normalized_domain or company.raw_domain,
                "description": company.description,
                "locations": json.loads(company.locations_json or "[]"),
                "industry_tags": json.loads(company.industry_tags_json or "[]"),
                "stage": link.stage,
                "disposition": link.disposition,
                "stage_reason": link.stage_reason,
                "fit_score": fit.fit_score if fit else None,
                "fit_decision": fit.decision if fit else None,
                "fit_reasons": json.loads(fit.reasons_json or "[]") if fit else [],
                "confidence": company.confidence,
                "has_draft": draft is not None,
                "updated_at": link.updated_at,
            }
        )
    return result


@router.get("/agent-activity")
def agent_activity(campaign_id: str | None = None, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    statement = select(AgentTask).order_by(AgentTask.updated_at.desc()).limit(100)
    if campaign_id:
        campaign = _campaign(session, campaign_id)
        statement = statement.where(AgentTask.campaign_id == campaign.id)
    tasks = session.exec(statement).all()
    return [
        {
            "id": item.task_id,
            "agent_role": item.agent_role,
            "task_type": item.task_type,
            "status": item.status,
            "progress": item.progress,
            "narrative": item.narrative,
            "attempt_count": item.attempt_count,
            "company_id": item.company_id,
            "updated_at": item.updated_at,
        }
        for item in tasks
    ]


@router.get("/exceptions")
def list_exceptions(status: str = "open", session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    statement = select(ReviewException).where(ReviewException.status == status).order_by(ReviewException.created_at.desc())
    items = session.exec(statement).all()
    company_ids = {item.company_id for item in items if item.company_id is not None}
    companies = {
        company.id: company
        for company in session.exec(select(Company).where(col(Company.id).in_(company_ids))).all()
        if company.id is not None
    } if company_ids else {}
    return [
        {
            "id": item.exception_id,
            "category": item.category,
            "title": item.title,
            "explanation": item.explanation,
            "recommended_action": item.recommended_action,
            "status": item.status,
            "campaign_id": item.campaign_id,
            "company_id": item.company_id,
            "company_name": companies[item.company_id].name if item.company_id in companies else None,
            "external_company_id": companies[item.company_id].company_id if item.company_id in companies else None,
            "created_at": item.created_at,
        }
        for item in items
    ]


@router.post("/exceptions/{exception_id}/resolve")
def resolve_exception(
    exception_id: str,
    payload: ExceptionResolution,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    item = session.exec(select(ReviewException).where(ReviewException.exception_id == exception_id)).first()
    if item is None:
        raise HTTPException(status_code=404, detail="Exception not found.")
    task = session.get(AgentTask, item.agent_task_id) if item.agent_task_id else None
    if payload.action == "retry" and task is not None:
        missing_contact = task.company_id is not None and session.exec(
            select(Contact).where(Contact.company_id == task.company_id)
        ).first() is None
        if task.task_type == "application_draft" and missing_contact:
            task.task_type = "contact_research"
            task.agent_role = "contact_researcher"
            task.run_id = None
            task.output_json = "{}"
            task.narrative = "The research specialist will look for a suitable public contact before drafting."
        else:
            task.narrative = "The specialist will retry with your guidance."
        task.status = "queued"
        task.attempt_count = 0
        task.available_at = utc_now()
        task.last_error = None
        session.add(task)
    elif payload.action == "skip" and item.company_id and item.campaign_id:
        link = session.exec(
            select(CampaignCompany).where(
                CampaignCompany.campaign_id == item.campaign_id,
                CampaignCompany.company_id == item.company_id,
            )
        ).first()
        if link is not None:
            link.stage = "archived"
            link.disposition = "user_skipped"
            link.stage_reason = payload.note or "Skipped from the exception inbox."
            link.updated_at = utc_now()
            session.add(link)
    item.status = "resolved"
    item.resolution = payload.note or payload.action
    item.resolved_by_user_id = request.state.user_id
    item.resolved_at = utc_now()
    item.updated_at = utc_now()
    session.add(item)
    session.commit()
    return {"id": item.exception_id, "status": item.status, "resolution": item.resolution}


def _run_roots(settings: Settings) -> list[Path]:
    scoped_root = scoped_runs_root(settings.runs_root).resolve()
    roots = [scoped_root]
    identity = current_identity()
    legacy_root = settings.runs_root.resolve()
    if legacy_root != scoped_root and (identity is None or identity.effective_workspace_id == 1):
        roots.append(legacy_root)
    return roots


def _tailored_cv_path(run_id: str, settings: Settings, suffix: str = ".pdf") -> Path | None:
    for root in _run_roots(settings):
        attachments = (root / run_id / "output" / "attachments").resolve()
        if not attachments.is_relative_to(root) or not attachments.is_dir():
            continue
        files = sorted(path.resolve() for path in attachments.glob(f"*{suffix}") if path.is_file())
        if files and files[0].is_relative_to(root):
            return files[0]
    return None


def _document_items(session: Session, settings: Settings, campaign_id: str | None = None) -> list[dict[str, Any]]:
    statement = select(Document).order_by(Document.created_at.desc())
    campaign_company_ids: set[int] | None = None
    if campaign_id:
        campaign = _campaign(session, campaign_id)
        statement = statement.where(Document.campaign_id == campaign.id)
        campaign_company_ids = {
            item.company_id
            for item in session.exec(select(CampaignCompany).where(CampaignCompany.campaign_id == campaign.id)).all()
        }
    documents = session.exec(statement).all()
    items = [
        {
            "id": item.document_id,
            "title": item.title,
            "type": item.document_type,
            "filename": item.filename,
            "mime_type": item.mime_type,
            "size_bytes": item.size_bytes,
            "campaign_id": item.campaign_id,
            "company_id": item.company_id,
            "status": item.status,
            "created_at": item.created_at,
            "preview_url": f"/documents/{item.document_id}/content",
        }
        for item in documents
    ]

    draft_statement = select(EmailDraft).order_by(EmailDraft.created_at.desc())
    if campaign_company_ids is not None:
        if not campaign_company_ids:
            drafts = []
        else:
            drafts = session.exec(draft_statement.where(EmailDraft.company_id.in_(campaign_company_ids))).all()
    else:
        drafts = session.exec(draft_statement).all()
    # Legacy smoke-test drafts have no imported application run and do not belong
    # in the user's application document library.
    drafts = [draft for draft in drafts if draft.imported_file_id is not None]
    company_ids = {draft.company_id for draft in drafts if draft.company_id is not None}
    companies = (
        session.exec(select(Company).where(Company.id.in_(company_ids))).all()
        if company_ids
        else []
    )
    company_names = {company.id: company.name for company in companies}
    imported_file_ids = {draft.imported_file_id for draft in drafts if draft.imported_file_id is not None}
    imported_files = (
        session.exec(select(ImportedFile).where(ImportedFile.id.in_(imported_file_ids))).all()
        if imported_file_ids
        else []
    )
    run_ids = {item.id: item.run_id for item in imported_files}
    for draft in drafts:
        company_name = company_names.get(draft.company_id) or draft.external_company_id or "Company"
        items.append(
            {
                "id": f"email-draft-{draft.id}",
                "title": f"{company_name} — {draft.subject}",
                "type": "email_draft",
                "filename": f"email-{draft.draft_id}.html",
                "mime_type": "text/html",
                "size_bytes": len(draft.body_text.encode("utf-8")),
                "campaign_id": None,
                "company_id": draft.company_id,
                "status": "ready",
                "created_at": draft.created_at,
                "preview_url": f"/documents/email-draft-{draft.id}/content",
            }
        )
        run_id = run_ids.get(draft.imported_file_id)
        cv_path = _tailored_cv_path(run_id, settings) if run_id else None
        if cv_path is not None:
            items.append(
                {
                    "id": f"tailored-cv-{draft.id}",
                    "title": f"{company_name} — Tailored CV",
                    "type": "tailored_cv",
                    "filename": cv_path.name,
                    "mime_type": "application/pdf",
                    "size_bytes": cv_path.stat().st_size,
                    "campaign_id": None,
                    "company_id": draft.company_id,
                    "status": "ready",
                    "created_at": draft.created_at,
                    "preview_url": f"/documents/tailored-cv-{draft.id}/content",
                    "download_url": f"/documents/tailored-cv-{draft.id}/download",
                }
            )

    if campaign_id is None:
        profile_specs = (
            (UserProfileSnapshot, "user-profile", "career_profile", "Career profile", "user-profile.json"),
            (MasterCvProfileSnapshot, "master-cv", "master_cv_profile", "Master CV profile", "master-cv-profile.json"),
            (PolicySnapshot, "policy", "outreach_policy", "Outreach preferences and boundaries", "outreach-policy.json"),
        )
        for model, slug, document_type, title, filename in profile_specs:
            snapshot = _approved(session, model)
            if snapshot is None:
                continue
            document_id = f"profile-{slug}-{snapshot.id}"
            items.append(
                {
                    "id": document_id,
                    "title": title,
                    "type": document_type,
                    "filename": filename,
                    "mime_type": "application/json",
                    "size_bytes": len(snapshot.raw_json.encode("utf-8")),
                    "campaign_id": None,
                    "company_id": None,
                    "status": "approved",
                    "created_at": snapshot.imported_at,
                    "preview_url": f"/documents/{document_id}/content",
                }
            )
    return items


@router.get("/documents")
def list_documents(
    campaign_id: str | None = None,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, Any]]:
    return _document_items(session, settings, campaign_id)


def _email_preview(draft: EmailDraft, company_name: str) -> HTMLResponse:
    subject = escape(draft.subject)
    body = escape(draft.body_text)
    company = escape(company_name)
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{subject}</title><style>
body {{ margin: 0; color: #17392d; background: #f3f0e8; font: 16px/1.65 Arial, sans-serif; }}
main {{ box-sizing: border-box; width: min(760px, calc(100% - 64px)); min-height: calc(100vh - 64px); margin: 32px auto; padding: 48px 56px; border: 1px solid #d8d5ca; border-radius: 10px; background: #fffefa; box-shadow: 0 18px 55px rgba(24, 50, 39, .09); }}
.label {{ margin: 0 0 8px; color: #6c7d75; font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }}
h1 {{ margin: 0 0 10px; font: 32px/1.2 Georgia, serif; }}
.company {{ margin: 0 0 34px; color: #6c7d75; }}
pre {{ margin: 0; white-space: pre-wrap; word-wrap: break-word; font: inherit; }}
</style></head><body><main><p class="label">Email prepared for</p><h1>{subject}</h1><p class="company">{company}</p><pre>{body}</pre></main></body></html>"""
    return HTMLResponse(
        content,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _profile_content(document_id: str, session: Session) -> Response | None:
    specs = (
        ("profile-user-profile-", UserProfileSnapshot, "Career profile", "user-profile.json"),
        ("profile-master-cv-", MasterCvProfileSnapshot, "Master CV profile", "master-cv-profile.json"),
        ("profile-policy-", PolicySnapshot, "Outreach preferences and boundaries", "outreach-policy.json"),
    )
    for prefix, model, title, filename in specs:
        if not document_id.startswith(prefix):
            continue
        try:
            snapshot_id = int(document_id.removeprefix(prefix))
        except ValueError:
            return None
        snapshot = session.exec(select(model).where(model.id == snapshot_id, model.status == "approved")).first()
        if snapshot is None:
            return None
        try:
            content = json.dumps(json.loads(snapshot.raw_json), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            content = snapshot.raw_json
        page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>{escape(title)}</title><style>
body {{ margin: 0; color: #17392d; background: #f3f0e8; font: 15px/1.6 Arial, sans-serif; }}
main {{ box-sizing: border-box; width: min(900px, calc(100% - 64px)); min-height: calc(100vh - 64px); margin: 32px auto; padding: 42px 50px; border: 1px solid #d8d5ca; border-radius: 10px; background: #fffefa; box-shadow: 0 18px 55px rgba(24, 50, 39, .09); }}
.label {{ margin: 0 0 8px; color: #6c7d75; font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; }}
h1 {{ margin: 0 0 28px; font: 32px/1.2 Georgia, serif; }}
pre {{ margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; font: 13px/1.55 Consolas, monospace; tab-size: 2; }}
</style></head><body><main><p class="label">Approved source of truth</p><h1>{escape(title)}</h1><pre>{escape(content)}</pre></main></body></html>"""
        return HTMLResponse(
            content=page,
            headers={
                "Cache-Control": "no-store",
                "Content-Disposition": f'inline; filename="{filename}"',
                "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
                "X-Content-Type-Options": "nosniff",
            },
        )
    return None


@router.get("/documents/{document_id}/content")
def document_content(
    document_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    if document_id.startswith("tailored-cv-"):
        try:
            draft_pk = int(document_id.removeprefix("tailored-cv-"))
        except ValueError:
            raise HTTPException(status_code=404, detail="Document not found.")
        draft = session.exec(select(EmailDraft).where(EmailDraft.id == draft_pk)).first()
        imported_file = (
            session.exec(select(ImportedFile).where(ImportedFile.id == draft.imported_file_id)).first()
            if draft is not None and draft.imported_file_id is not None
            else None
        )
        path = _tailored_cv_path(imported_file.run_id, settings) if imported_file is not None else None
        if path is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        html_path = _tailored_cv_path(imported_file.run_id, settings, ".html")
        if html_path is not None:
            html_content = html_path.read_text(encoding="utf-8", errors="replace")
            html_content = re.sub(
                r'(?i)(\bsrc\s*=\s*)(["\'])file:[^"\']*\2',
                r'\1\2data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==\2',
                html_content,
            )
            return HTMLResponse(
                html_content,
                headers={
                    "Cache-Control": "no-store",
                    "Content-Disposition": f'inline; filename="{html_path.name}"',
                    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
                    "X-Content-Type-Options": "nosniff",
                },
            )
        return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")
    if document_id.startswith("email-draft-"):
        try:
            draft_pk = int(document_id.removeprefix("email-draft-"))
        except ValueError:
            raise HTTPException(status_code=404, detail="Document not found.")
        draft = session.exec(select(EmailDraft).where(EmailDraft.id == draft_pk)).first()
        if draft is None:
            raise HTTPException(status_code=404, detail="Document not found.")
        company = session.exec(select(Company).where(Company.id == draft.company_id)).first() if draft.company_id else None
        return _email_preview(draft, company.name if company else draft.external_company_id)
    profile_content = _profile_content(document_id, session)
    if profile_content is not None:
        return profile_content
    document = session.exec(select(Document).where(Document.document_id == document_id)).first()
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    root = scoped_runs_root(settings.runs_root).resolve()
    path = (root / Path(document.relative_path)).resolve()
    if not path.is_relative_to(root) or not path.is_file():
        raise HTTPException(status_code=404, detail="Document file is unavailable.")
    return FileResponse(path, media_type=document.mime_type, filename=document.filename, content_disposition_type="inline")


@router.get("/documents/{document_id}/download")
def document_download(
    document_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    if not document_id.startswith("tailored-cv-"):
        raise HTTPException(status_code=404, detail="Document not found.")
    try:
        draft_pk = int(document_id.removeprefix("tailored-cv-"))
    except ValueError:
        raise HTTPException(status_code=404, detail="Document not found.")
    draft = session.exec(select(EmailDraft).where(EmailDraft.id == draft_pk)).first()
    imported_file = (
        session.exec(select(ImportedFile).where(ImportedFile.id == draft.imported_file_id)).first()
        if draft is not None and draft.imported_file_id is not None
        else None
    )
    path = _tailored_cv_path(imported_file.run_id, settings) if imported_file is not None else None
    if path is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline")


@router.get("/product/summary")
def product_summary(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    campaigns = session.exec(select(Campaign).order_by(Campaign.updated_at.desc())).all()
    links = session.exec(select(CampaignCompany)).all()
    tasks = session.exec(
        select(AgentTask).where(AgentTask.status.in_(["queued", "retry", "running"])).order_by(AgentTask.updated_at.desc())
    ).all()
    exceptions = session.exec(select(ReviewException).where(ReviewException.status == "open")).all()
    documents = _document_items(session, settings)
    sent = session.exec(select(SentMessage).where(SentMessage.status == "provider_accepted")).all()
    stages = Counter(item.stage for item in links)
    linked_company_ids = {item.company_id for item in links}
    drafts = session.exec(select(EmailDraft)).all()
    drafted_company_ids = {item.company_id for item in drafts if item.company_id is not None}
    drafted_external_ids = {item.external_company_id for item in drafts}
    contacted = session.exec(
        select(OutreachRecord).where(
            OutreachRecord.status.in_(["sent", "provider_accepted", "outcome_uncertain"])
        )
    ).all()
    contacted_company_ids = {item.company_id for item in contacted if item.company_id is not None}
    contacted_policy_keys = {item.company_policy_key for item in contacted}
    for company in session.exec(select(Company)).all():
        if company.id in linked_company_ids:
            continue
        if company.id in contacted_company_ids or company.company_policy_key in contacted_policy_keys:
            stages["sent"] += 1
        elif company.id in drafted_company_ids or company.company_id in drafted_external_ids:
            stages["ready"] += 1
        else:
            stages["discovered"] += 1
    return {
        "campaigns": [_campaign_response(item, session) for item in campaigns],
        "active_campaign": _campaign_response(campaigns[0], session) if campaigns else None,
        "pipeline": dict(stages),
        "active_tasks": [
            {
                "id": item.task_id,
                "agent_role": item.agent_role,
                "status": item.status,
                "progress": item.progress,
                "narrative": item.narrative,
            }
            for item in tasks[:8]
        ],
        "exception_count": len(exceptions),
        "document_count": len(documents),
        "sent_count": len(sent),
    }


BUILTIN_JOB_SOURCES = {
    "greenhouse.io": "verification_capable",
    "lever.co": "verification_capable",
    "myworkdayjobs.com": "verification_capable",
    "smartrecruiters.com": "verification_capable",
    "jobs.personio.de": "verification_capable",
    "ashbyhq.com": "verification_capable",
    "jobs.ch": "verification_capable",
    "jobup.ch": "verification_capable",
    "jobscout24.ch": "verification_capable",
    "arbeitsagentur.de": "verification_capable",
    "bund.de": "verification_capable",
}


def _job_response(job: JobPosting, session: Session, *, campaign_job: CampaignJob | None = None) -> dict[str, Any]:
    company = session.get(Company, job.company_id) if job.company_id else None
    fit = session.exec(
        select(JobFitEvaluation).where(JobFitEvaluation.job_posting_id == job.id).order_by(JobFitEvaluation.created_at.desc())
    ).first()
    package = None
    if campaign_job is not None:
        package = session.exec(
            select(JobApplicationPackage).where(JobApplicationPackage.campaign_job_id == campaign_job.id).order_by(JobApplicationPackage.created_at.desc())
        ).first()
    return {
        "id": job.job_id,
        "title": job.title,
        "company_id": company.company_id if company else job.external_company_id,
        "company_name": company.name if company else None,
        "source_url": job.source_url,
        "canonical_url": job.canonical_url,
        "application_url": job.application_url,
        "employer_website_url": job.employer_website_url,
        "source_domain": job.source_domain,
        "source_kind": job.source_kind,
        "description": job.description,
        "locations": json.loads(job.locations_json or "[]"),
        "remote_policy": job.remote_policy,
        "employment_types": json.loads(job.employment_types_json or "[]"),
        "compensation": json.loads(job.compensation_json or "{}"),
        "languages": json.loads(job.languages_json or "[]"),
        "requirements": json.loads(job.requirements_json or "[]"),
        "responsibilities": json.loads(job.responsibilities_json or "[]"),
        "date_posted": job.date_posted,
        "valid_through": job.valid_through,
        "first_seen_at": job.first_seen_at,
        "last_verified_at": job.last_verified_at,
        "vacancy_status": job.vacancy_status,
        "verification_evidence": json.loads(job.verification_evidence_json or "{}"),
        "confidence": job.confidence,
        "review_flags": json.loads(job.review_flags_json or "[]"),
        "company_fit_score": fit.company_fit_score if fit else None,
        "role_fit_score": fit.role_fit_score if fit else None,
        "fit_decision": fit.decision if fit else None,
        "fit_reasons": json.loads(fit.reasons_json or "[]") if fit else [],
        "fit_gaps": json.loads(fit.gaps_json or "[]") if fit else [],
        "application_status": campaign_job.application_status if campaign_job else None,
        "application_note": campaign_job.status_note if campaign_job else None,
        "package_ready": package is not None,
        "answer_kit": json.loads(package.answer_kit_json or "[]") if package else [],
        "cover_letter_text": package.cover_letter_text if package else None,
    }


@router.get("/jobs")
def list_jobs(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return [_job_response(job, session) for job in session.exec(select(JobPosting).order_by(JobPosting.updated_at.desc())).all()]


@router.get("/jobs/{job_id}")
def get_job(job_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    job = session.exec(select(JobPosting).where(JobPosting.job_id == job_id)).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job posting not found.")
    campaign_job = session.exec(select(CampaignJob).where(CampaignJob.job_posting_id == job.id)).first()
    return _job_response(job, session, campaign_job=campaign_job)


@router.get("/campaigns/{campaign_id}/jobs")
def campaign_jobs(campaign_id: str, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    campaign = _campaign(session, campaign_id)
    links = session.exec(select(CampaignJob).where(CampaignJob.campaign_id == campaign.id).order_by(CampaignJob.updated_at.desc())).all()
    return [_job_response(job, session, campaign_job=link) for link in links if (job := session.get(JobPosting, link.job_posting_id))]


@router.post("/campaigns/{campaign_id}/refresh", status_code=202)
def refresh_job_campaign(campaign_id: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    campaign = _campaign(session, campaign_id)
    if campaign.campaign_type != "listed_job_search":
        raise HTTPException(status_code=409, detail="Only job-listing campaigns support vacancy refresh.")
    task = AgentTask(
        task_id=f"task-{uuid4()}", campaign_id=campaign.id, agent_role="vacancy_scout", task_type="job_research",
        narrative="Refreshing discovery and revalidating active vacancies.", workspace_id=campaign.workspace_id,
    )
    session.add(task)
    campaign.status = "researching"
    campaign.updated_at = utc_now()
    session.add(campaign)
    session.commit()
    return {"campaign_id": campaign.campaign_id, "task_id": task.task_id, "status": "queued"}


@router.patch("/campaigns/{campaign_id}/jobs/{job_id}/application-status")
def update_job_application_status(campaign_id: str, job_id: str, payload: JobApplicationStatusUpdate, session: Session = Depends(get_session)) -> dict[str, Any]:
    campaign = _campaign(session, campaign_id)
    job = session.exec(select(JobPosting).where(JobPosting.job_id == job_id)).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job posting not found.")
    link = session.exec(select(CampaignJob).where(CampaignJob.campaign_id == campaign.id, CampaignJob.job_posting_id == job.id)).first()
    if link is None:
        raise HTTPException(status_code=404, detail="Job is not part of this campaign.")
    link.application_status = payload.status
    link.status_note = payload.note
    link.applied_at = utc_now() if payload.status == "applied" and link.applied_at is None else link.applied_at
    link.updated_at = utc_now()
    session.add(link)
    session.add(AuditLog(actor_type="user", action="job_application_status_updated", entity_type="job_posting", entity_id=job.job_id, result_status=payload.status, metadata_json=json.dumps({"campaign_id": campaign.campaign_id})))
    session.commit()
    return _job_response(job, session, campaign_job=link)


@router.get("/settings/job-sources")
def list_job_sources(session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    identity = current_identity()
    if identity is None:
        raise HTTPException(status_code=409, detail="Job source settings require a workspace.")
    existing = {item.domain: item for item in session.exec(select(JobSourceTrust)).all()}
    for domain, trust_level in BUILTIN_JOB_SOURCES.items():
        if domain not in existing:
            item = JobSourceTrust(domain=domain, trust_level=trust_level, is_builtin=True, workspace_id=identity.effective_workspace_id)
            session.add(item)
            existing[domain] = item
    session.commit()
    return [{"domain": item.domain, "trust_level": item.trust_level, "enabled": item.enabled, "is_builtin": item.is_builtin} for item in sorted(existing.values(), key=lambda value: value.domain)]


@router.put("/settings/job-sources/{domain}")
def update_job_source(domain: str, payload: JobSourceTrustUpdate, session: Session = Depends(get_session)) -> dict[str, Any]:
    identity = current_identity()
    normalized = payload.domain.strip().lower().removeprefix("www.")
    if normalized != domain.strip().lower().removeprefix("www."):
        raise HTTPException(status_code=422, detail="Path and payload domains must match.")
    item = session.exec(select(JobSourceTrust).where(JobSourceTrust.domain == normalized)).first()
    if item is None:
        item = JobSourceTrust(domain=normalized, workspace_id=identity.effective_workspace_id if identity else 0)
    item.trust_level = payload.trust_level
    item.enabled = payload.enabled
    item.updated_at = utc_now()
    session.add(item)
    session.commit()
    return {"domain": item.domain, "trust_level": item.trust_level, "enabled": item.enabled, "is_builtin": item.is_builtin}
