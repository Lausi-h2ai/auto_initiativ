from __future__ import annotations

import hashlib
import json
import shutil
import re
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
    UserProfileSnapshot,
)
from backend.app.master_cv.contracts import MasterCvClaimProposals, MasterCvDocument, PortraitCrop
from backend.app.master_cv.rendering import render_master_cv_html
from backend.app.master_cv.pdf import render_master_cv_pdf
from backend.app.master_cv.templates import get_master_cv_template


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

    def approved_user_profile(self) -> tuple[UserProfileSnapshot, dict] | None:
        snapshot = self.session.exec(
            select(UserProfileSnapshot)
            .where(UserProfileSnapshot.status == "approved")
            .order_by(UserProfileSnapshot.imported_at.desc())
        ).first()
        return (snapshot, json.loads(snapshot.raw_json)) if snapshot else None

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
        candidate["lifecycle_status"] = "candidate"
        candidate["revision"] = 1
        document = MasterCvDocument.model_validate(candidate)
        version_number = self._next_version_number()
        candidate_snapshot = MasterCvDocumentSnapshot(
            document_snapshot_id=document.document_snapshot_id,
            master_cv_profile_snapshot_id=profile_snapshot.id,
            user_profile_snapshot_id=self._approved_user_profile_id(),
            parent_snapshot_id=latest.id if latest is not None else None,
            schema_version=document.schema_version,
            version_number=version_number,
            title=document.title,
            template_id=document.design.template_id,
            template_version=document.design.template_version,
            locale=document.locale,
            market=document.market,
            page_count=document.design.page_count,
            page_goal=document.page_goal,
            portrait_variant_id=document.portrait_variant_id,
            review_flags_json=json.dumps(document.review_flags),
            content_hash=self._document_hash(document),
            status="candidate",
            raw_json=document.model_dump_json(),
        )
        self.session.add(candidate_snapshot)
        self.session.flush()
        run_id = f"master-cv-{uuid4().hex}"
        record = MasterCvBuilderSession(
            session_id=f"mcvs_{uuid4().hex}",
            run_id=run_id,
            base_document_snapshot_id=latest.id if latest is not None else None,
            current_candidate_snapshot_id=candidate_snapshot.id,
            candidate_json=document.model_dump_json(),
            candidate_revision=document.revision,
            status="active",
        )
        self.session.add(record)
        self.session.flush()
        self._materialize_source_documents(run_id)
        self._audit("master_cv_session_started", "master_cv_builder_session", record.session_id, run_id=run_id)
        self.session.commit()
        self.session.refresh(record)
        return record

    def update_candidate(
        self,
        record: MasterCvBuilderSession,
        candidate: dict,
        *,
        expected_revision: int | None = None,
    ) -> MasterCvDocument:
        current = MasterCvDocument.model_validate_json(record.candidate_json)
        if expected_revision is not None and current.revision != expected_revision:
            raise MasterCvValidationError(
                f"Stale candidate revision {expected_revision}; current revision is {current.revision}."
            )
        candidate["revision"] = current.revision + 1
        candidate["content_hash"] = None
        document = MasterCvDocument.model_validate(candidate)
        approved = self.approved_profile()
        if approved is None or document.profile_id != approved[1].get("profile_id"):
            raise MasterCvValidationError("Candidate must reference the current approved master CV profile.")
        document = self._enforce_claim_text_integrity(document, approved[1])
        get_master_cv_template(document.design.template_id)
        snapshot, document = self._ensure_mutable_candidate_snapshot(
            record, document, approved[0]
        )
        document.content_hash = self._document_hash(document)
        record.candidate_json = document.model_dump_json()
        record.candidate_revision = document.revision
        record.updated_at = utc_now()
        self.session.add(record)
        snapshot.title = document.title
        snapshot.template_id = document.design.template_id
        snapshot.locale = document.locale
        snapshot.page_count = document.design.page_count
        snapshot.template_version = document.design.template_version
        snapshot.market = document.market
        snapshot.page_goal = document.page_goal
        snapshot.portrait_variant_id = document.portrait_variant_id
        snapshot.review_flags_json = json.dumps(document.review_flags)
        snapshot.content_hash = document.content_hash
        snapshot.raw_json = document.model_dump_json()
        snapshot.updated_at = utc_now()
        self.session.add(snapshot)
        self._audit("master_cv_candidate_updated", "master_cv_document_snapshot", snapshot.document_snapshot_id)
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
        expected_revision = patch.pop("expected_revision", None)
        allowed = {"template_id", "template_version", "page_size", "page_count", "density", "accent_color", "font_family", "photo"}
        unexpected = set(patch) - allowed
        if unexpected:
            raise MasterCvValidationError(f"Unsupported design fields: {', '.join(sorted(unexpected))}")
        candidate["design"] = {**candidate.get("design", {}), **patch}
        if "page_count" in patch:
            candidate["page_goal"] = patch["page_count"]
        return self.update_candidate(record, candidate, expected_revision=expected_revision)

    def patch_block(self, block_id: str, patch: dict) -> MasterCvDocument:
        record = self._require_active_session()
        candidate = json.loads(record.candidate_json)
        expected_revision = patch.pop("expected_revision", None)
        allowed = {"text", "visible"}
        unexpected = set(patch) - allowed
        if unexpected:
            raise MasterCvValidationError(f"Unsupported block fields: {', '.join(sorted(unexpected))}")
        for section in candidate.get("sections", []):
            for block in section.get("blocks", []):
                if block.get("block_id") == block_id:
                    if "text" in patch and patch["text"] != block.get("text"):
                        metadata = dict(block.get("metadata") or {})
                        metadata.update({
                            "needs_review": True,
                            "review_reason": "Direct text edits require factual review before approval.",
                            "previous_claim_refs": list(block.get("claim_refs") or []),
                        })
                        block["metadata"] = metadata
                        block["claim_refs"] = []
                        candidate["lifecycle_status"] = "needs_review"
                        flags = set(candidate.get("review_flags") or [])
                        flags.add(f"unsupported_direct_edit:{block_id}")
                        candidate["review_flags"] = sorted(flags)
                    block.update(patch)
                    return self.update_candidate(record, candidate, expected_revision=expected_revision)
        raise MasterCvValidationError(f"Unknown block: {block_id}")

    def approve_candidate(self) -> MasterCvDocumentSnapshot:
        record = self._require_active_session()
        document = MasterCvDocument.model_validate_json(record.candidate_json)
        template = get_master_cv_template(document.design.template_id)
        if document.design.template_version != template.template_version:
            raise MasterCvValidationError("Candidate references an unsupported template version.")
        if document.design.page_count not in template.supported_pages:
            raise MasterCvValidationError("Candidate page goal is unsupported by the selected template.")
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
        profile_field_refs: set[str] = set()
        review_block_ids: list[str] = []
        for section in document.sections:
            for block in section.blocks:
                referenced.update(block.claim_refs)
                profile_field_refs.update(block.profile_field_refs)
                if block.metadata and block.metadata.get("needs_review"):
                    review_block_ids.append(block.block_id)
        unsupported = referenced - set(claims)
        if unsupported:
            raise MasterCvValidationError("Candidate references unsupported claims: " + ", ".join(sorted(unsupported)))
        approved_user_profile = self.approved_user_profile()
        allowed_profile_fields = self._json_field_paths(approved_user_profile[1]) if approved_user_profile else set()
        unsupported_profile_fields = profile_field_refs - allowed_profile_fields
        if unsupported_profile_fields:
            raise MasterCvValidationError(
                "Candidate references unsupported profile fields: " + ", ".join(sorted(unsupported_profile_fields))
            )
        if review_block_ids:
            raise MasterCvValidationError(
                "Candidate blocks still need review: " + ", ".join(sorted(review_block_ids))
            )
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

        if document.lifecycle_status == "needs_review" or document.review_flags:
            raise MasterCvValidationError("Candidate still has review blockers.")
        metrics = self.render_metrics(document)
        if metrics["overflow"]:
            raise MasterCvValidationError(
                f"Candidate content overflows the {document.design.page_count}-page goal."
            )
        raw_json = document.model_dump_json()
        now = utc_now()
        snapshot = self._candidate_snapshot(document.document_snapshot_id)
        if snapshot is None or snapshot.status != "candidate":
            raise MasterCvValidationError("Candidate snapshot is unavailable or was already approved.")
        document.lifecycle_status = "approved"
        document.content_hash = self._document_hash(document)
        snapshot.portrait_asset_id = asset.id if asset is not None else None
        snapshot.content_hash = document.content_hash
        snapshot.status = "approved"
        snapshot.raw_json = document.model_dump_json()
        snapshot.approved_at = now
        snapshot.updated_at = now
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

    def candidate(self, document_snapshot_id: str) -> MasterCvDocumentSnapshot | None:
        return self._candidate_snapshot(document_snapshot_id)

    def restore_version(self, document_snapshot_id: str) -> MasterCvBuilderSession:
        source = self.session.exec(select(MasterCvDocumentSnapshot).where(
            MasterCvDocumentSnapshot.document_snapshot_id == document_snapshot_id,
            MasterCvDocumentSnapshot.status == "approved",
        )).first()
        if source is None:
            raise MasterCvValidationError("Approved Master CV version not found.")
        active = self.active_session()
        if active is not None:
            active.status = "closed"
            active.completed_at = utc_now()
            self.session.add(active)
            self.session.commit()
        document = MasterCvDocument.model_validate_json(source.raw_json)
        document.document_snapshot_id = f"mastercv_{uuid4().hex}"
        document.created_at = utc_now()
        document.lifecycle_status = "candidate"
        document.review_flags = []
        document.revision = 1
        document.content_hash = None
        profile = self.approved_profile()
        if profile is None:
            raise MasterCvValidationError("An approved master CV profile is required.")
        snapshot = MasterCvDocumentSnapshot(
            document_snapshot_id=document.document_snapshot_id,
            master_cv_profile_snapshot_id=profile[0].id,
            user_profile_snapshot_id=self._approved_user_profile_id(),
            parent_snapshot_id=source.id,
            schema_version=document.schema_version,
            version_number=self._next_version_number(),
            title=document.title,
            template_id=document.design.template_id,
            template_version=document.design.template_version,
            locale=document.locale,
            market=document.market,
            page_count=document.design.page_count,
            page_goal=document.page_goal,
            portrait_variant_id=document.portrait_variant_id,
            review_flags_json=json.dumps(document.review_flags),
            content_hash=self._document_hash(document),
            status="candidate",
            raw_json=document.model_dump_json(),
        )
        self.session.add(snapshot)
        self.session.flush()
        record = MasterCvBuilderSession(
            session_id=f"mcvs_{uuid4().hex}", run_id=f"master-cv-{uuid4().hex}",
            base_document_snapshot_id=source.id, candidate_json=document.model_dump_json(), status="active",
            current_candidate_snapshot_id=snapshot.id, candidate_revision=document.revision,
        )
        self.session.add(record)
        self._audit("master_cv_version_restored", "master_cv_document_snapshot", document.document_snapshot_id)
        self.session.commit()
        self.session.refresh(record)
        return record

    def approve_claim_proposal(self, proposal_id: str) -> MasterCvProfileSnapshot:
        record = self.active_session()
        if record is None:
            raise MasterCvValidationError("No active Master CV session owns this proposal.")
        path = scoped_runs_root(self.settings.runs_root) / record.run_id / "output" / "master_cv_claim_proposals.json"
        try:
            proposals = MasterCvClaimProposals.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise MasterCvValidationError("No schema-valid claim proposals are available.") from exc
        proposal = next((item for item in proposals.proposals if item.proposal_id == proposal_id), None)
        if proposal is None:
            raise MasterCvValidationError("Claim proposal not found in this session.")
        if not proposal.source_refs:
            raise MasterCvValidationError("Claim proposal has no factual provenance.")
        approved = self.approved_profile()
        if approved is None or proposals.profile_id != approved[1].get("profile_id"):
            raise MasterCvValidationError("Claim proposal references a stale claim ledger.")
        previous, payload = approved
        next_payload = json.loads(json.dumps(payload))
        claim_id = f"claim_{uuid4().hex}"
        next_payload["profile_id"] = f"profile_{uuid4().hex}"
        next_payload["created_at"] = utc_now().isoformat()
        next_payload.setdefault("claims", []).append({
            "claim_id": claim_id,
            "category": proposal.category,
            "statement": proposal.statement,
            "approved_for_tailoring": True,
            "provenance": {
                "source_type": "user_claim",
                "confidence": proposal.confidence if proposal.confidence is not None else 1,
                "needs_review": False,
                "source_refs": proposal.source_refs,
            },
        })
        raw = json.dumps(next_payload, ensure_ascii=False, sort_keys=True)
        snapshot = MasterCvProfileSnapshot(
            profile_id=next_payload["profile_id"], schema_version="1.0",
            source_created_at=utc_now(), content_hash=hashlib.sha256(raw.encode("utf-8")).hexdigest(),
            status="approved", raw_json=raw,
        )
        previous.status = "superseded"
        record.status = "closed"
        record.completed_at = utc_now()
        record.updated_at = utc_now()
        self.session.add_all([previous, snapshot, record])
        self._audit("master_cv_claim_proposal_approved", "master_cv_profile_snapshot", next_payload["profile_id"], run_id=record.run_id)
        self.session.commit()
        self.session.refresh(snapshot)
        return snapshot

    def render_candidate(self) -> str:
        record = self._require_active_session()
        document = MasterCvDocument.model_validate_json(record.candidate_json)
        asset = None
        if document.portrait_asset_id:
            asset = self.session.exec(select(ProfileAsset).where(ProfileAsset.asset_id == document.portrait_asset_id)).first()
        return render_master_cv_html(document, portrait_data_uri=self._portrait_uri(asset))

    @staticmethod
    def render_metrics(document: MasterCvDocument) -> dict[str, int | bool]:
        estimated_lines = 5
        for section in document.sections:
            visible = [block for block in section.blocks if block.visible]
            if not visible:
                continue
            estimated_lines += 2
            for block in visible:
                estimated_lines += max(1, (len(block.text) + 89) // 90) + 1
        capacity = 58 * document.design.page_count
        return {
            "page_goal": document.design.page_count,
            "estimated_lines": estimated_lines,
            "overflow": estimated_lines > capacity,
        }

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
        pdf_path = output / "master_cv.pdf"
        json_path.write_text(document.model_dump_json(indent=2), encoding="utf-8")
        html_path.write_text(
            render_master_cv_html(document, portrait_data_uri=self._portrait_uri(asset)),
            encoding="utf-8",
        )
        pdf_path.write_bytes(render_master_cv_pdf(document))
        base = scoped_runs_root(self.settings.runs_root)
        for kind, path, mime in (
            ("master_cv_source", json_path, "application/json"),
            ("master_cv", html_path, "text/html"),
            ("master_cv", pdf_path, "application/pdf"),
        ):
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

    def _materialize_source_documents(self, run_id: str) -> None:
        root = scoped_runs_root(self.settings.runs_root).resolve()
        destination_root = root / run_id / "input"
        destination_root.mkdir(parents=True, exist_ok=True)
        sources = self.session.exec(select(Document).where(
            Document.document_type == "master_cv_source_upload",
        ).order_by(Document.created_at.asc())).all()
        for source in sources:
            origin = (root / source.relative_path).resolve()
            if not origin.is_relative_to(root) or not origin.is_file():
                continue
            destination = destination_root / Path(source.filename).name
            if destination.exists():
                destination = destination_root / f"{source.document_id}-{Path(source.filename).name}"
            shutil.copyfile(origin, destination)
            extracted = origin.with_name(origin.name + ".extracted.json")
            if extracted.is_file() and extracted.is_relative_to(root):
                shutil.copyfile(extracted, destination.with_name(destination.name + ".extracted.json"))

    def _candidate_snapshot(self, document_snapshot_id: str) -> MasterCvDocumentSnapshot | None:
        return self.session.exec(select(MasterCvDocumentSnapshot).where(
            MasterCvDocumentSnapshot.document_snapshot_id == document_snapshot_id,
        )).first()

    def _ensure_mutable_candidate_snapshot(
        self,
        record: MasterCvBuilderSession,
        document: MasterCvDocument,
        profile_snapshot: MasterCvProfileSnapshot,
    ) -> tuple[MasterCvDocumentSnapshot, MasterCvDocument]:
        """Materialize legacy session-only drafts without mutating approved versions."""

        existing = self._candidate_snapshot(document.document_snapshot_id)
        if existing is not None and existing.status == "candidate":
            record.current_candidate_snapshot_id = existing.id
            return existing, document

        parent_id = existing.id if existing is not None and existing.status == "approved" else record.base_document_snapshot_id
        if existing is not None:
            document.document_snapshot_id = f"mastercv_{uuid4().hex}"
            document.created_at = utc_now()
        document.lifecycle_status = "needs_review" if document.review_flags else "candidate"
        document.content_hash = self._document_hash(document)
        snapshot = MasterCvDocumentSnapshot(
            document_snapshot_id=document.document_snapshot_id,
            master_cv_profile_snapshot_id=profile_snapshot.id,
            user_profile_snapshot_id=self._approved_user_profile_id(),
            parent_snapshot_id=parent_id,
            schema_version=document.schema_version,
            version_number=self._next_version_number(),
            title=document.title,
            template_id=document.design.template_id,
            template_version=document.design.template_version,
            locale=document.locale,
            market=document.market,
            page_count=document.design.page_count,
            page_goal=document.page_goal,
            portrait_variant_id=document.portrait_variant_id,
            review_flags_json=json.dumps(document.review_flags),
            content_hash=document.content_hash,
            status="candidate",
            raw_json=document.model_dump_json(),
        )
        self.session.add(snapshot)
        self.session.flush()
        record.current_candidate_snapshot_id = snapshot.id
        self._audit(
            "master_cv_legacy_candidate_materialized",
            "master_cv_document_snapshot",
            snapshot.document_snapshot_id,
            run_id=record.run_id,
        )
        return snapshot, document

    def _approved_user_profile_id(self) -> int | None:
        approved = self.approved_user_profile()
        return approved[0].id if approved else None

    @staticmethod
    def _json_field_paths(payload: dict, prefix: str = "") -> set[str]:
        paths: set[str] = set()
        for key, value in payload.items():
            path = f"{prefix}.{key}" if prefix else key
            paths.add(path)
            if isinstance(value, dict):
                paths.update(MasterCvService._json_field_paths(value, path))
        return paths

    def _next_version_number(self) -> int:
        versions = self.session.exec(select(MasterCvDocumentSnapshot.version_number)).all()
        return max(versions, default=0) + 1

    @staticmethod
    def _document_hash(document: MasterCvDocument) -> str:
        payload = document.model_dump(mode="json", exclude={"content_hash"})
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    @staticmethod
    def _enforce_claim_text_integrity(document: MasterCvDocument, profile: dict) -> MasterCvDocument:
        statements = {
            claim.get("claim_id"): claim.get("statement", "")
            for claim in profile.get("claims", [])
            if claim.get("approved_for_tailoring") is True
        }
        flags = set(document.review_flags)
        for section in document.sections:
            for block in section.blocks:
                if (
                    block.visible and block.text.strip() and block.kind not in {"heading", "contact"}
                    and not block.claim_refs and not block.profile_field_refs
                ):
                    metadata = dict(block.metadata or {})
                    metadata.update({
                        "needs_review": True,
                        "review_reason": "Factual content has no approved claim or profile-field reference.",
                    })
                    block.metadata = metadata
                    flags.add(f"unsupported_content:{block.block_id}")
                    continue
                if not block.claim_refs:
                    continue
                normalized_text = re.sub(r"\s+", " ", block.text).strip().casefold()
                supported = len(block.claim_refs) == 1 and normalized_text == re.sub(
                    r"\s+", " ", statements.get(block.claim_refs[0], "")
                ).strip().casefold()
                if supported:
                    continue
                metadata = dict(block.metadata or {})
                metadata.update({
                    "needs_review": True,
                    "review_reason": "Wording differs from the exact approved claim and requires factual review.",
                })
                block.metadata = metadata
                flags.add(f"claim_wording_changed:{block.block_id}")
        if flags:
            document.lifecycle_status = "needs_review"
            document.review_flags = sorted(flags)
        return document

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
            "market": "international",
            "page_goal": 1,
            "portrait_asset_id": None,
            "portrait_variant_id": None,
            "lifecycle_status": "candidate",
            "review_flags": [],
            "revision": 1,
            "content_hash": None,
            "design": {
                "template_id": "classic-ats", "template_version": "1.0", "page_size": "A4", "page_count": 1,
                "density": "balanced", "photo": {"enabled": False, "shape": "rounded", "position": "header_right", "inclusion_policy": "german_swiss"},
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
