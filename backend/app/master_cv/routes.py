from __future__ import annotations

import json
import base64
import hashlib
from dataclasses import asdict
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, HTMLResponse
from sqlmodel import Session, select

from backend.app.agents.master_cv_builder_prompt import (
    build_master_cv_builder_instructions,
    build_master_cv_start_message,
)
from backend.app.agents.master_cv_builder_runtime import PiRpcMasterCvBuilderAdapter
from backend.app.auth.context import current_workspace_id, scoped_runs_root
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import Document, MasterCvBuilderSession, MasterCvDocumentSnapshot, ProfileAsset
from backend.app.db.session import get_session
from backend.app.master_cv.contracts import BuilderChatRequest, FocalPoint, MasterCvDocument, PortraitCrop
from backend.app.master_cv.portraits import PortraitService, PortraitValidationError
from backend.app.master_cv.service import MasterCvService, MasterCvValidationError, utc_now
from backend.app.master_cv.templates import MASTER_CV_TEMPLATES, upstream_prompt_path, upstream_skill_path
from backend.app.onboarding.document_text import DocumentExtractionError, extract_document_text


router = APIRouter(prefix="/master-cv", tags=["master-cv"])


def get_builder_adapter(settings: Settings = Depends(get_settings)) -> PiRpcMasterCvBuilderAdapter:
    return PiRpcMasterCvBuilderAdapter(settings=settings)


def _service(session: Session, settings: Settings) -> MasterCvService:
    return MasterCvService(session=session, settings=settings)


def _candidate(record: MasterCvBuilderSession | None) -> dict | None:
    if record is None or not record.candidate_json:
        return None
    candidate = json.loads(record.candidate_json)
    candidate["preview_url"] = "/master-cv/preview"
    return candidate


def _version(item) -> dict:
    return {
        "document_snapshot_id": item.document_snapshot_id,
        "version_number": item.version_number,
        "version": item.version_number,
        "title": item.title,
        "template_id": item.template_id,
        "locale": item.locale,
        "page_count": item.page_count,
        "status": item.status,
        "created_at": item.created_at.isoformat(),
        "approved_at": item.approved_at.isoformat() if item.approved_at else None,
        "preview_url": f"/master-cv/versions/{item.document_snapshot_id}/preview",
    }


def _template(item) -> dict:
    data = asdict(item)
    data.update({
        "id": item.template_id,
        "note": item.description,
        "market": "DACH" if "germany" in item.markets or "switzerland" in item.markets else "Global",
        "photo": item.supports_photo,
        "ats": "High" if item.ats_compatibility == "high" else "Good",
        "ats_profile": "high" if item.ats_compatibility == "high" else "moderate",
        "layout": item.layout,
        "portrait_placement": item.portrait_placement,
        "supported_markets": list(item.supported_locales),
    })
    return data


@router.get("/templates")
def list_templates() -> list[dict]:
    return [_template(template) for template in MASTER_CV_TEMPLATES]


@router.get("/approved")
def approved_master_cv(
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings),
) -> dict | None:
    item = _service(session, settings).latest_document()
    return _version(item) if item else None


@router.get("/versions")
def list_versions(
    session: Session = Depends(get_session), settings: Settings = Depends(get_settings),
) -> list[dict]:
    return [_version(item) for item in _service(session, settings).versions()]


@router.get("/summary")
def summary(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    service = _service(session, settings)
    approved_profile = service.approved_profile()
    active = service.active_session()
    approved = service.latest_document()
    portrait = session.exec(select(ProfileAsset).where(ProfileAsset.status == "ready").order_by(ProfileAsset.created_at.desc())).first()
    sources = session.exec(
        select(Document).where(Document.document_type == "master_cv_source_upload").order_by(Document.created_at.desc())
    ).all()
    return {
        "has_approved_profile": approved_profile is not None,
        "claims": [
            {
                **claim,
                "id": claim.get("claim_id"),
                "text": claim.get("statement"),
                "needs_review": claim.get("provenance", {}).get("needs_review", False),
                "status": "approved" if claim.get("approved_for_tailoring") else "candidate",
            }
            for claim in (approved_profile[1].get("claims", []) if approved_profile else [])
        ],
        "candidate": _candidate(active),
        "session": {
            "session_id": active.session_id, "run_id": active.run_id, "status": active.status,
            "transcript": json.loads(active.transcript_json or "[]"),
        } if active else None,
        "approved": _version(approved) if approved else None,
        "versions": [_version(item) for item in service.versions()],
        "portrait": {
            "asset_id": portrait.asset_id, "mime_type": portrait.mime_type, "width": portrait.width,
            "height": portrait.height, "crop": json.loads(portrait.crop_json),
            "focal_point": json.loads(portrait.focal_point_json), "status": portrait.status,
            "filename": portrait.original_filename,
            "preview_url": f"/master-cv/portrait/{portrait.asset_id}/preview",
        } if portrait else None,
        "source_documents": [
            {"id": item.document_id, "document_id": item.document_id, "title": item.title, "filename": item.filename, "status": item.status}
            for item in sources
        ],
        "templates": [_template(template) for template in MASTER_CV_TEMPLATES],
    }


@router.post("/sessions/start")
def start_session(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    adapter: PiRpcMasterCvBuilderAdapter = Depends(get_builder_adapter),
) -> dict:
    service = _service(session, settings)
    try:
        record = service.start_session()
        profile = service.approved_profile()
        assert profile is not None
        guidance = "\n\n".join(
            path.read_text(encoding="utf-8")
            for path in (upstream_skill_path(), upstream_prompt_path("interview"), upstream_prompt_path("beautify"))
        )
        adapter.prepare_agent_workspace(
            record.run_id,
            build_master_cv_builder_instructions(
                run_id=record.run_id,
                profile=profile[1],
                template_catalog=[asdict(item) for item in MASTER_CV_TEMPLATES],
                starting_document=json.loads(record.candidate_json),
                upstream_guidance=guidance,
            ),
        )
        adapter.start_or_attach(record.run_id)
        adapter.ensure_recruiter_prompt(
            record.run_id,
            build_master_cv_start_message(record.run_id),
            require_plain_reply=False,
        )
        service.import_agent_candidate(record)
        transcript = adapter.transcript_entries(record.run_id)
        record.transcript_json = json.dumps(transcript, ensure_ascii=False)
        record.updated_at = utc_now()
        session.add(record)
        session.commit()
        return {"session_id": record.session_id, "run_id": record.run_id, "status": record.status, "candidate": _candidate(record), "transcript": transcript}
    except (MasterCvValidationError, OSError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        # The durable candidate remains usable through direct editing when the
        # local Pi runtime is unavailable; expose the transport issue explicitly.
        return {
            "session_id": record.session_id,
            "run_id": record.run_id,
            "status": "agent_unavailable",
            "candidate": _candidate(record),
            "transcript": [],
            "error": str(exc),
        }


@router.get("/sessions/{session_id}/status")
def session_status(session_id: str, session: Session = Depends(get_session)) -> dict:
    record = session.exec(select(MasterCvBuilderSession).where(
        MasterCvBuilderSession.session_id == session_id,
    )).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Master CV session not found")
    candidate = MasterCvDocument.model_validate_json(record.candidate_json)
    return {
        "session_id": record.session_id, "run_id": record.run_id, "status": record.status,
        "candidate_id": candidate.document_snapshot_id, "revision": candidate.revision,
        "started_at": record.started_at.isoformat(),
        "completed_at": record.completed_at.isoformat() if record.completed_at else None,
    }


@router.post("/sessions/{session_id}/start")
def start_named_session(
    session_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    record = session.exec(select(MasterCvBuilderSession).where(
        MasterCvBuilderSession.session_id == session_id,
    )).first()
    if record is None or record.status != "active":
        raise HTTPException(status_code=404, detail="Active master CV session not found")
    return {
        "session_id": record.session_id, "run_id": record.run_id, "status": record.status,
        "candidate": _candidate(record), "transcript": json.loads(record.transcript_json or "[]"),
    }


@router.post("/sessions/{session_id}/finish")
def finish_session(session_id: str, session: Session = Depends(get_session)) -> dict:
    record = session.exec(select(MasterCvBuilderSession).where(
        MasterCvBuilderSession.session_id == session_id,
    )).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Master CV session not found")
    record.status = "closed"
    record.completed_at = utc_now()
    record.updated_at = utc_now()
    session.add(record)
    session.commit()
    return {"session_id": record.session_id, "status": record.status}


@router.post("/sessions/{session_id}/reset")
def reset_session(
    session_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    record = session.exec(select(MasterCvBuilderSession).where(
        MasterCvBuilderSession.session_id == session_id,
    )).first()
    if record is None:
        raise HTTPException(status_code=404, detail="Master CV session not found")
    base = session.get(MasterCvDocumentSnapshot, record.base_document_snapshot_id) if record.base_document_snapshot_id else None
    record.status = "closed"
    record.completed_at = utc_now()
    session.add(record)
    session.commit()
    try:
        next_record = _service(session, settings).restore_version(base.document_snapshot_id) if base else _service(session, settings).start_session()
    except MasterCvValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"session_id": next_record.session_id, "run_id": next_record.run_id, "status": next_record.status, "candidate": _candidate(next_record)}


@router.post("/sessions/{session_id}/messages")
def send_message(
    session_id: str,
    payload: BuilderChatRequest,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
    adapter: PiRpcMasterCvBuilderAdapter = Depends(get_builder_adapter),
) -> dict:
    record = session.exec(select(MasterCvBuilderSession).where(MasterCvBuilderSession.session_id == session_id)).first()
    if record is None or record.status != "active":
        raise HTTPException(status_code=404, detail="Active master CV session not found")
    try:
        reply = adapter.send_message(record.run_id, payload.message)
        _service(session, settings).import_agent_candidate(record)
        transcript = adapter.transcript_entries(record.run_id)
        record.transcript_json = json.dumps(transcript, ensure_ascii=False)
        record.updated_at = utc_now()
        session.add(record)
        session.commit()
        return {"session_id": record.session_id, "run_id": record.run_id, "reply": reply.message, "candidate": _candidate(record), "transcript": transcript}
    except (MasterCvValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/session")
def close_session(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    record = _service(session, settings).active_session()
    if record is None:
        return {"status": "not_started"}
    record.status = "closed"
    record.completed_at = utc_now()
    record.updated_at = utc_now()
    session.add(record)
    session.commit()
    return {"status": "closed", "session_id": record.session_id}


@router.patch("/candidate/design")
async def patch_design(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        document = _service(session, settings).patch_design(await request.json())
        return document.model_dump(mode="json")
    except (MasterCvValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/candidate/blocks/{block_id}")
async def patch_block(
    block_id: str,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        document = _service(session, settings).patch_block(block_id, await request.json())
        return document.model_dump(mode="json")
    except (MasterCvValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/candidates/{document_snapshot_id}/blocks/{block_id}")
async def patch_candidate_block(
    document_snapshot_id: str,
    block_id: str,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    record = _service(session, settings).active_session()
    if record is None or MasterCvDocument.model_validate_json(record.candidate_json).document_snapshot_id != document_snapshot_id:
        raise HTTPException(status_code=404, detail="Active candidate not found")
    return await patch_block(block_id, request, session, settings)


@router.post("/render")
def render_candidate(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        service = _service(session, settings)
        record = service.active_session()
        if record is None:
            raise MasterCvValidationError("No active master CV builder session.")
        document = MasterCvDocument.model_validate_json(record.candidate_json)
        service.render_candidate()
        metrics = service.render_metrics(document)
        return {
            "status": "overflow" if metrics["overflow"] else "ready",
            "preview_url": "/master-cv/preview",
            **metrics,
        }
    except (MasterCvValidationError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/candidates/{document_snapshot_id}/render")
def render_named_candidate(
    document_snapshot_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    record = _service(session, settings).active_session()
    if record is None or MasterCvDocument.model_validate_json(record.candidate_json).document_snapshot_id != document_snapshot_id:
        raise HTTPException(status_code=404, detail="Active candidate not found")
    return render_candidate(session, settings)


@router.get("/preview", response_class=HTMLResponse)
def preview_candidate(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> str:
    try:
        return _service(session, settings).render_candidate()
    except (MasterCvValidationError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/versions/{document_snapshot_id}/preview", response_class=HTMLResponse)
def preview_version(
    document_snapshot_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> str:
    from backend.app.db.models import MasterCvDocumentSnapshot
    from backend.app.master_cv.rendering import render_master_cv_html

    snapshot = session.exec(
        select(MasterCvDocumentSnapshot).where(
            MasterCvDocumentSnapshot.document_snapshot_id == document_snapshot_id,
            MasterCvDocumentSnapshot.status == "approved",
        )
    ).first()
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Approved master CV version not found")
    document = MasterCvDocument.model_validate_json(snapshot.raw_json)
    asset = session.get(ProfileAsset, snapshot.portrait_asset_id) if snapshot.portrait_asset_id else None
    return render_master_cv_html(document, portrait_data_uri=_service(session, settings)._portrait_uri(asset))


@router.post("/approve")
def approve_candidate(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        return _version(_service(session, settings).approve_candidate())
    except (MasterCvValidationError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/candidates/{document_snapshot_id}/approve")
def approve_named_candidate(
    document_snapshot_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    record = _service(session, settings).active_session()
    if record is None or MasterCvDocument.model_validate_json(record.candidate_json).document_snapshot_id != document_snapshot_id:
        raise HTTPException(status_code=404, detail="Active candidate not found")
    return approve_candidate(session, settings)


@router.post("/versions/{document_snapshot_id}/restore")
def restore_version(
    document_snapshot_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        record = _service(session, settings).restore_version(document_snapshot_id)
    except MasterCvValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {"session_id": record.session_id, "run_id": record.run_id, "status": record.status, "candidate": _candidate(record)}


@router.post("/claim-proposals/{proposal_id}/approve")
def approve_claim_proposal(
    proposal_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    try:
        snapshot = _service(session, settings).approve_claim_proposal(proposal_id)
    except MasterCvValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {
        "status": snapshot.status,
        "profile_id": snapshot.profile_id,
        "message": "Claim approved into a new immutable profile snapshot. Start a new Master CV candidate to use it.",
    }


@router.put("/source-documents/{filename}")
async def upload_source_document(
    filename: str,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    clean = Path(filename).name
    if clean != filename or not clean or Path(clean).suffix.lower() not in {".pdf", ".doc", ".docx", ".txt", ".md", ".json"}:
        raise HTTPException(status_code=422, detail="Unsupported source document filename")
    content = await request.body()
    if not content or len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="Source document must be between 1 byte and 20 MB")
    record = _service(session, settings).active_session()
    run_id = record.run_id if record else "master-cv-sources"
    root = scoped_runs_root(settings.runs_root)
    destination = root / run_id / "input" / clean
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(content)
    try:
        extracted = extract_document_text(destination)
    except (DocumentExtractionError, OSError, ValueError) as exc:
        extracted = {"filename": clean, "text": "", "error": str(exc), "needs_review": True}
    destination.with_name(destination.name + ".extracted.json").write_text(
        json.dumps(extracted, ensure_ascii=False), encoding="utf-8",
    )
    document = Document(
        document_id=f"doc_{uuid4().hex}", run_id=run_id, document_type="master_cv_source_upload",
        title=clean, filename=clean, relative_path=destination.relative_to(root).as_posix(),
        mime_type=request.headers.get("content-type", "application/octet-stream"), size_bytes=len(content),
        content_hash=hashlib.sha256(content).hexdigest(),
    )
    session.add(document)
    session.commit()
    return {"document_id": document.document_id, "filename": clean, "status": "ready"}


@router.put("/portrait/{filename}")
async def upload_portrait(
    filename: str,
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    workspace_key = f"workspace_{current_workspace_id() or 0}"
    service = PortraitService(settings.runs_root / "master_cv_assets")
    try:
        result = service.ingest(
            workspace_key=workspace_key,
            filename=filename,
            content=await request.body(),
            declared_mime_type=request.headers.get("content-type"),
        )
    except PortraitValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    asset = ProfileAsset(
        asset_id=result.asset_id, original_filename=result.original_filename, mime_type=result.mime_type,
        relative_path=result.relative_path, content_hash=result.content_hash, size_bytes=result.size_bytes,
        width=result.width, height=result.height, crop_json=result.crop.model_dump_json(),
        focal_point_json=result.focal_point.model_dump_json(), status="ready",
    )
    session.add(asset)
    active = _service(session, settings).active_session()
    if active is not None:
        candidate = json.loads(active.candidate_json)
        candidate["portrait_asset_id"] = asset.asset_id
        candidate["design"]["photo"]["enabled"] = True
        active.candidate_json = MasterCvDocument.model_validate(candidate).model_dump_json()
        active.updated_at = utc_now()
        session.add(active)
    session.commit()
    return {
        "asset_id": asset.asset_id, "mime_type": asset.mime_type, "width": asset.width, "height": asset.height,
        "crop": result.crop.model_dump(), "focal_point": result.focal_point.model_dump(), "status": asset.status,
    }


@router.post("/portrait")
async def upload_portrait_canonical(
    request: Request,
    filename: str | None = Header(default=None, alias="X-Filename"),
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict:
    if not filename:
        raise HTTPException(status_code=422, detail="X-Filename header is required")
    return await upload_portrait(filename, request, session, settings)


@router.patch("/portrait")
async def update_portrait_crop(
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    asset = session.exec(select(ProfileAsset).where(ProfileAsset.status == "ready").order_by(ProfileAsset.created_at.desc())).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="Portrait not found")
    payload = await request.json()
    crop_payload = payload.get("crop", payload)
    if "zoom" in crop_payload:
        zoom = max(float(crop_payload.get("zoom", 1)), 1)
        width = height = 1 / zoom
        x = min(max(float(crop_payload.get("x", 0.5)) - width / 2, 0), 1 - width)
        y = min(max(float(crop_payload.get("y", 0.5)) - height / 2, 0), 1 - height)
        crop_payload = {"x": x, "y": y, "width": width, "height": height}
    try:
        crop = PortraitCrop.model_validate(crop_payload)
        focal = FocalPoint.model_validate(payload.get("focal_point", {"x": 0.5, "y": 0.5}))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    asset.crop_json = crop.model_dump_json()
    asset.focal_point_json = focal.model_dump_json()
    asset.updated_at = utc_now()
    session.add(asset)
    session.commit()
    return {"asset_id": asset.asset_id, "crop": crop.model_dump(), "focal_point": focal.model_dump(), "status": asset.status}


@router.post("/portrait/{asset_id}/crop")
async def crop_named_portrait(
    asset_id: str,
    request: Request,
    session: Session = Depends(get_session),
) -> dict:
    asset = session.exec(select(ProfileAsset).where(
        ProfileAsset.asset_id == asset_id, ProfileAsset.status == "ready",
    )).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="Portrait not found")
    payload = await request.json()
    try:
        crop = PortraitCrop.model_validate(payload.get("crop", payload))
        focal = FocalPoint.model_validate(payload.get("focal_point", json.loads(asset.focal_point_json)))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    asset.crop_json = crop.model_dump_json()
    asset.focal_point_json = focal.model_dump_json()
    asset.updated_at = utc_now()
    session.add(asset)
    session.commit()
    return {"asset_id": asset.asset_id, "crop": crop.model_dump(), "focal_point": focal.model_dump(), "status": asset.status}


@router.get("/portrait/{asset_id}/preview")
def portrait_preview(
    asset_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Response:
    asset = session.exec(
        select(ProfileAsset).where(ProfileAsset.asset_id == asset_id, ProfileAsset.status == "ready")
    ).first()
    if asset is None:
        raise HTTPException(status_code=404, detail="Portrait not found")
    try:
        uri = PortraitService(settings.runs_root / "master_cv_assets").render_data_uri(
            relative_path=asset.relative_path,
            expected_sha256=asset.content_hash,
            crop=PortraitCrop.model_validate_json(asset.crop_json),
        )
    except PortraitValidationError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return Response(
        content=base64.b64decode(uri.partition(",")[2]),
        media_type="image/jpeg",
        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.get("/documents/{document_snapshot_id}/preview", response_class=HTMLResponse)
def document_preview(
    document_snapshot_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> str:
    return preview_version(document_snapshot_id, session, settings)


@router.get("/documents/{document_snapshot_id}/download")
def document_download(
    document_snapshot_id: str,
    format: str = "pdf",
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> FileResponse:
    if format not in {"pdf", "html"}:
        raise HTTPException(status_code=422, detail="Format must be pdf or html")
    mime = "application/pdf" if format == "pdf" else "text/html"
    documents = session.exec(select(Document).where(Document.document_type == "master_cv", Document.mime_type == mime)).all()
    match = next((item for item in documents if json.loads(item.provenance_json or "{}").get("master_cv_document_snapshot_id") == document_snapshot_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Generated Master CV document not found")
    root = scoped_runs_root(settings.runs_root)
    path = (root / match.relative_path).resolve()
    if not path.is_relative_to(root.resolve()) or not path.is_file():
        raise HTTPException(status_code=409, detail="Generated Master CV file is unavailable")
    return FileResponse(path, media_type=mime, filename=match.filename)
