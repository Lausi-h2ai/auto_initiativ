from __future__ import annotations

from sqlmodel import Session, select

from backend.app.agents.application_draft import application_draft_template_html
from backend.app.core.config import Settings
from backend.app.db.models import MasterCvDocumentSnapshot, ProfileAsset
from backend.app.master_cv.contracts import MasterCvDocument, PortraitCrop
from backend.app.master_cv.portraits import PortraitService
from backend.app.master_cv.rendering import render_master_cv_html


def approved_master_cv_html(
    session: Session,
    settings: Settings,
    *,
    document_snapshot_id: int | None = None,
) -> str:
    """Resolve the exact latest approved design for a downstream tailoring run.

    The returned HTML contains only validated structured text and, if selected,
    a hash-verified application-owned portrait data URI. The neutral repository
    template remains the deterministic fallback before the first approval.
    """

    if document_snapshot_id is not None:
        snapshot = session.get(MasterCvDocumentSnapshot, document_snapshot_id)
        if snapshot is None or snapshot.status != "approved":
            raise ValueError("Campaign-pinned Master CV snapshot is unavailable")
    else:
        snapshot = session.exec(
            select(MasterCvDocumentSnapshot)
            .where(MasterCvDocumentSnapshot.status == "approved")
            .order_by(MasterCvDocumentSnapshot.version_number.desc())
        ).first()
    if snapshot is None:
        return application_draft_template_html()
    document = MasterCvDocument.model_validate_json(snapshot.raw_json)
    portrait_uri = None
    if snapshot.portrait_asset_id is not None:
        asset = session.get(ProfileAsset, snapshot.portrait_asset_id)
        if asset is None or asset.status != "ready":
            raise ValueError("Approved master CV references an unavailable portrait asset")
        portrait_uri = PortraitService(settings.runs_root / "master_cv_assets").render_data_uri(
            relative_path=asset.relative_path,
            expected_sha256=asset.content_hash,
            crop=PortraitCrop.model_validate_json(asset.crop_json),
        )
    return render_master_cv_html(document, portrait_data_uri=portrait_uri)
