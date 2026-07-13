from __future__ import annotations

import json
from html import escape
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend.app.auth.context import current_identity, scoped_runs_root
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import (
    AgentTask,
    Campaign,
    CampaignCompany,
    Company,
    Document,
    EmailDraft,
    FitEvaluation,
    GmailConnection,
    MasterCvProfileSnapshot,
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
    name: str = Field(min_length=1, max_length=160)
    role_focus: str = Field(default="Profile-aligned roles", min_length=1, max_length=240)
    locations: list[str] = Field(default_factory=list, max_length=20)
    company_preferences: str | None = Field(default=None, max_length=2000)
    notes: str | None = Field(default=None, max_length=2000)
    time_budget_minutes: int = Field(default=30, ge=1, le=240)
    max_companies: int = Field(default=30, ge=1, le=100)
    sending_mode: Literal["prepare_only", "gated_autosend"] = "prepare_only"


class CampaignModeUpdate(BaseModel):
    sending_mode: Literal["prepare_only", "gated_autosend"]


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
        "status": campaign.status,
        "sending_mode": campaign.sending_mode,
        "brief": json.loads(campaign.brief_json or "{}"),
        "stages": dict(stages),
        "company_count": len(links),
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
        task.status = "queued"
        task.attempt_count = 0
        task.available_at = utc_now()
        task.last_error = None
        task.narrative = "The specialist will retry with your guidance."
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


def _document_items(session: Session, campaign_id: str | None = None) -> list[dict[str, Any]]:
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
    company_ids = {draft.company_id for draft in drafts if draft.company_id is not None}
    companies = (
        session.exec(select(Company).where(Company.id.in_(company_ids))).all()
        if company_ids
        else []
    )
    company_names = {company.id: company.name for company in companies}
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
def list_documents(campaign_id: str | None = None, session: Session = Depends(get_session)) -> list[dict[str, Any]]:
    return _document_items(session, campaign_id)


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


@router.get("/product/summary")
def product_summary(session: Session = Depends(get_session)) -> dict[str, Any]:
    campaigns = session.exec(select(Campaign).order_by(Campaign.updated_at.desc())).all()
    links = session.exec(select(CampaignCompany)).all()
    tasks = session.exec(
        select(AgentTask).where(AgentTask.status.in_(["queued", "retry", "running"])).order_by(AgentTask.updated_at.desc())
    ).all()
    exceptions = session.exec(select(ReviewException).where(ReviewException.status == "open")).all()
    documents = _document_items(session)
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
