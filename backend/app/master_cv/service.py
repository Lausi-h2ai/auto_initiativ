from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlmodel import Session, select

from backend.app.auth.context import current_workspace_id, scoped_runs_root
from backend.app.core.config import Settings
from backend.app.db.models import (
    AuditLog,
    Document,
    MasterCvBuilderSession,
    MasterCvDocumentSnapshot,
    MasterCvProfileSnapshot,
    ProfileAsset,
)
from backend.app.master_cv.contracts import MasterCvDocument, PortraitCrop
from backend.app.master_cv.rendering import render_master_cv_html


class MasterCvValidationError(ValueError):
    pass


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MasterCvService:
    def __init__(self, *, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def approved_profile(self) -> tuple[MasterCvProfileSnapshot, dict] | None:
        snapshot = self.session.exec(
            select(MasterCvProfileSnapshot)
            .where(MasterCvProfileSnapshot.status == "approved")
            .order_by(MasterCvProfileSnapshot.imported_at.desc())
        ).first()
        if snapshot is None:
            return None
        return snapshot, json.loads(snapshot.raw_json)

    def active_session(self) -> MasterCvBuilderSession | None:
        return self.session.exec(
            select(MasterCvBuilderSession)
            .where(MasterCvBuilderSession.status == "active")
            .order_by(MasterCvBuilderSession.updated_at.desc())
        ).first()

    def start_session(self) -> MasterCvBuilderSession:
        existing = self.active_session()
        if existing is not None:
            return existing
        approved = self.approved_profile()
        if approved is None:
            raise MasterCvValidationError("An approved master CV profile is required before building a design.")
        profile_snapshot, profile = approved
        latest = self.latest_document()
        candidate = json.loads(latest.raw_json) if latest is not None else self._default_candidate(profile)
        candidate["document_snapshot_id"] = f"mastercv_{uuid4().hex}"
        candidate["created_at"] = utc_now().isoformat()
        run_id = f"master-cv-{uuid4().hex}"
        record = MasterCvBuilderSession(
            session_id=f"mcvs_{uuid4().hex}",
            run_id=run_id,
            base_document_snapshot_id=latest.id if latest is not None else None,
            candidate_json=json.dumps(candidate, ensure_ascii=False, sort_keys=True),
            status="active",
        )
        self.session.add(record)
        self.session.flush()
        self._audit("master_cv_session_started", "master_cv_builder_session", record.session_id, run_id=run_id)
        self.session.commit()
        self.session.refresh(record)
        return record

    def update_candidate(self, record: MasterCvBuilderSession, candidate: dict) -> MasterCvDocument:
        document = MasterCvDocument.model_validate(candidate)
        approved = self.approved_profile()
        if approved is None or document.profile_id != approved[1].get("profile_id"):
            raise MasterCvValidationError("Candidate must reference the current approved master CV profile.")
        record.candidate_json = document.model_dump_json()
        record.updated_at = utc_now()
        self.session.add(record)
        self.session.commit()
        return document

    def import_agent_candidate(self, record: MasterCvBuilderSession) -> MasterCvDocument | None:
        path = scoped_runs_root(self.settings.runs_root) / record.run_id / "output" / "master_cv_document.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise MasterCvValidationError("Builder agent produced invalid candidate JSON.") from exc
        return self.update_candidate(record, payload)

    def patch_design(self, patch: dict) -> MasterCvDocument:
        record = self._require_active_session()
        candidate = json.loads(record.candidate_json)
        allowed = {"template_id", "page_size", "page_count", "density", "accent_color", "font_family", "photo"}
        unexpected = set(patch) - allowed
        if unexpected:
            raise MasterCvValidationError(f"Unsupported design fields: {', '.join(sorted(unexpected))}")
        candidate["design"] = {**candidate.get("design", {}), **patch}
        return self.update_candidate(record, candidate)

    def patch_block(self, block_id: str, patch: dict) -> MasterCvDocument:
        record = self._require_active_session()
        candidate = json.loads(record.candidate_json)
        allowed = {"text", "visible", "claim_refs"}
        unexpected = set(patch) - allowed
        if unexpected:
            raise MasterCvValidationError(f"Unsupported block fields: {', '.join(sorted(unexpected))}")
        for section in candidate.get("sections", []):
            for block in section.get("blocks", []):
                if block.get("block_id") == block_id:
                    block.update(patch)
                    return self.update_candidate(record, candidate)
        raise MasterCvValidationError(f"Unknown block: {block_id}")

    def approve_candidate(self) -> MasterCvDocumentSnapshot:
        record = self._require_active_session()
        document = MasterCvDocument.model_validate_json(record.candidate_json)
        approved = self.approved_profile()
        if approved is None:
            raise MasterCvValidationError("The claim ledger is not approved.")
        profile_snapshot, profile = approved
        claims = {
            claim["claim_id"]: claim
            for claim in profile.get("claims", [])
            if claim.get("approved_for_tailoring") is True and not claim.get("provenance", {}).get("needs_review", False)
        }
        referenced: set[str] = set()
        for section in document.sections:
            for block in section.blocks:
                referenced.update(block.claim_refs)
                if block.metadata and block.metadata.get("needs_review"):
                    raise MasterCvValidationError(f"Block {block.block_id} still needs review.")
        unsupported = referenced - set(claims)
        if unsupported:
            raise MasterCvValidationError("Candidate references unsupported claims: " + ", ".join(sorted(unsupported)))
        if not referenced:
            raise MasterCvValidationError("At least one approved claim must be included before approval.")
        if document.portrait_asset_id is not None:
            asset = self.session.exec(
                select(ProfileAsset).where(
                    ProfileAsset.asset_id == document.portrait_asset_id,
                    ProfileAsset.status == "ready",
                )
            ).first()
            if asset is None:
                raise MasterCvValidationError("The selected portrait is unavailable.")
        else:
            asset = None

        current_versions = self.session.exec(select(MasterCvDocumentSnapshot)).all()
        version_number = max((item.version_number for item in current_versions), default=0) + 1
        raw_json = document.model_dump_json()
        now = utc_now()
        snapshot = MasterCvDocumentSnapshot(
            document_snapshot_id=document.document_snapshot_id,
            master_cv_profile_snapshot_id=profile_snapshot.id,
            parent_snapshot_id=record.base_document_snapshot_id,
            portrait_asset_id=asset.id if asset is not None else None,
            schema_version=document.schema_version,
            version_number=version_number,
            title=document.title,
            template_id=document.design.template_id,
            locale=document.locale,
            page_count=document.design.page_count,
            content_hash=hashlib.sha256(raw_json.encode("utf-8")).hexdigest(),
            status="approved",
            raw_json=raw_json,
            approved_at=now,
        )
        self.session.add(snapshot)
        record.status = "completed"
        record.completed_at = now
        record.updated_at = now
        self.session.add(record)
        self.session.flush()
        self._write_approved_documents(snapshot, document, asset)
        self._audit("master_cv_approved", "master_cv_document_snapshot", snapshot.document_snapshot_id, run_id=record.run_id)
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def latest_document(self) -> MasterCvDocumentSnapshot | None:
        return self.session.exec(
            select(MasterCvDocumentSnapshot)
            .where(MasterCvDocumentSnapshot.status == "approved")
            .order_by(MasterCvDocumentSnapshot.version_number.desc())
        ).first()

    def versions(self) -> list[MasterCvDocumentSnapshot]:
        return list(self.session.exec(
            select(MasterCvDocumentSnapshot).order_by(MasterCvDocumentSnapshot.version_number.desc())
        ).all())

    def render_candidate(self) -> str:
        record = self._require_active_session()
        document = MasterCvDocument.model_validate_json(record.candidate_json)
        asset = None
        if document.portrait_asset_id:
            asset = self.session.exec(select(ProfileAsset).where(ProfileAsset.asset_id == document.portrait_asset_id)).first()
        return render_master_cv_html(document, portrait_data_uri=self._portrait_uri(asset))

    def _write_approved_documents(
        self,
        snapshot: MasterCvDocumentSnapshot,
        document: MasterCvDocument,
        asset: ProfileAsset | None,
    ) -> None:
        output = scoped_runs_root(self.settings.runs_root) / "master-cv" / snapshot.document_snapshot_id
        output.mkdir(parents=True, exist_ok=True)
        json_path = output / "master_cv_document.json"
        html_path = output / "master_cv.html"
        json_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
        html_path.write_text(
            render_master_cv_html(document, portrait_data_uri=self._portrait_uri(asset)),
            encoding="utf-8",
        )
        base = scoped_runs_root(self.settings.runs_root)
        for kind, path, mime in (("master_cv_source", json_path, "application/json"), ("master_cv", html_path, "text/html")):
            content = path.read_bytes()
            self.session.add(Document(
                document_id=f"doc_{uuid4().hex}",
                run_id="master-cv",
                document_type=kind,
                title=f"{document.title} v{snapshot.version_number}",
                filename=path.name,
                relative_path=path.relative_to(base).as_posix(),
                mime_type=mime,
                size_bytes=len(content),
                content_hash=hashlib.sha256(content).hexdigest(),
                provenance_json=json.dumps({
                    "master_cv_document_snapshot_id": snapshot.document_snapshot_id,
                    "master_cv_profile_snapshot_id": document.profile_id,
                    "template_id": document.design.template_id,
                    "portrait_asset_id": document.portrait_asset_id,
                }, sort_keys=True),
            ))

    def _portrait_uri(self, asset: ProfileAsset | None) -> str | None:
        if asset is None:
            return None
        from backend.app.master_cv.portraits import PortraitService

        return PortraitService(self.settings.runs_root / "master_cv_assets").render_data_uri(
            relative_path=asset.relative_path,
            expected_sha256=asset.content_hash,
            crop=PortraitCrop.model_validate_json(asset.crop_json),
        )

    def _require_active_session(self) -> MasterCvBuilderSession:
        record = self.active_session()
        if record is None:
            raise MasterCvValidationError("No active master CV builder session.")
        return record

    def _default_candidate(self, profile: dict) -> dict:
        section_order = ["experience", "projects", "education", "skills", "languages", "certifications", "achievements", "custom"]
        type_by_category = {
            "experience": "experience", "project": "projects", "education": "education", "skill": "skills",
            "language": "languages", "certification": "certifications", "achievement": "achievements",
        }
        grouped: dict[str, list[dict]] = {key: [] for key in section_order}
        for index, claim in enumerate(profile.get("claims", [])):
            if not claim.get("approved_for_tailoring") or claim.get("provenance", {}).get("needs_review"):
                continue
            section_type = type_by_category.get(claim.get("category"), "custom")
            kind = "skill" if section_type in {"skills", "languages"} else "entry"
            grouped[section_type].append({
                "block_id": f"claim-{index + 1}",
                "kind": kind,
                "text": claim["statement"],
                "claim_refs": [claim["claim_id"]],
                "visible": True,
            })
        sections = [
            {"section_id": f"section-{kind}", "type": kind, "title": kind.replace("_", " ").title(), "blocks": grouped[kind]}
            for kind in section_order if grouped[kind]
        ]
        return {
            "schema_version": "1.0",
            "document_snapshot_id": f"mastercv_{uuid4().hex}",
            "profile_id": profile["profile_id"],
            "created_at": utc_now().isoformat(),
            "title": "Master CV",
            "locale": "en",
            "portrait_asset_id": None,
            "design": {
                "template_id": "classic-ats", "page_size": "A4", "page_count": 1,
                "density": "balanced", "photo": {"enabled": False, "shape": "rounded", "position": "header_right"},
            },
            "sections": sections,
        }

    def _audit(self, action: str, entity_type: str, entity_id: str, *, run_id: str | None = None) -> None:
        self.session.add(AuditLog(
            run_id=run_id,
            actor_type="user",
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            result_status="success",
        ))
