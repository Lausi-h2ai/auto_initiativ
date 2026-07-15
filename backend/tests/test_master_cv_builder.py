from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from sqlmodel import select

from backend.app.core.config import get_settings
from backend.app.db.models import Document, MasterCvProfileSnapshot
from backend.app.master_cv.contracts import MasterCvDocument
from backend.app.master_cv.downstream import approved_master_cv_html
from backend.app.master_cv.rendering import render_master_cv_html
from backend.app.master_cv.service import MasterCvService, MasterCvValidationError


def _profile() -> dict:
    return {
        "schema_version": "1.0",
        "profile_id": "profile-master-cv-test",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "claims": [
            {
                "claim_id": "claim-approved",
                "category": "experience",
                "statement": "Led a documented transformation program.",
                "approved_for_tailoring": True,
                "provenance": {
                    "source_type": "user_claim", "confidence": 1, "needs_review": False,
                    "source_refs": ["onboarding_chat:user_confirmation"],
                },
            }
        ],
    }


def test_renderer_escapes_content_and_keeps_only_verified_portrait_uri():
    document = MasterCvDocument.model_validate({
        "schema_version": "1.0",
        "document_snapshot_id": "mastercv_test",
        "profile_id": "profile_test",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": "Master <CV>",
        "design": {
            "template_id": "swiss", "page_size": "A4", "page_count": 1, "density": "balanced",
            "photo": {"enabled": True, "shape": "rounded", "position": "header_right"},
        },
        "sections": [{
            "section_id": "experience", "type": "experience", "title": "Experience",
            "blocks": [{
                "block_id": "entry-1", "kind": "entry", "text": "<script>alert(1)</script>",
                "claim_refs": ["claim-1"], "visible": True,
            }],
        }],
    })

    html = render_master_cv_html(document, portrait_data_uri="data:image/jpeg;base64,AA==")

    assert "<script>alert" not in html
    assert "&lt;script&gt;alert" in html
    assert 'data-tailoring-required="true"' in html
    assert "size: A4" in html

    with pytest.raises(ValueError, match="application-owned JPEG"):
        render_master_cv_html(document, portrait_data_uri="https://example.test/photo.jpg")


def test_service_creates_candidate_and_immutable_approved_documents(db_session, runs_root):
    profile = _profile()
    db_session.add(MasterCvProfileSnapshot(
        profile_id=profile["profile_id"], schema_version="1.0", content_hash="profile-hash",
        status="approved", raw_json=json.dumps(profile), source_created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()
    settings = get_settings()
    service = MasterCvService(session=db_session, settings=settings)

    builder = service.start_session()
    candidate = json.loads(builder.candidate_json)
    assert candidate["profile_id"] == profile["profile_id"]
    assert candidate["sections"][0]["blocks"][0]["claim_refs"] == ["claim-approved"]

    snapshot = service.approve_candidate()

    assert snapshot.status == "approved"
    assert snapshot.version_number == 1
    documents = db_session.exec(select(Document).where(Document.document_type == "master_cv")).all()
    assert len(documents) == 1
    assert (runs_root / documents[0].relative_path).exists()
    downstream_html = approved_master_cv_html(db_session, settings)
    assert 'data-master-cv-template="classic-ats"' in downstream_html
    assert "Led a documented transformation program." in downstream_html


def test_service_blocks_unapproved_claim_reference(db_session):
    profile = _profile()
    db_session.add(MasterCvProfileSnapshot(
        profile_id=profile["profile_id"], schema_version="1.0", content_hash="profile-hash-2",
        status="approved", raw_json=json.dumps(profile), source_created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()
    service = MasterCvService(session=db_session, settings=get_settings())
    builder = service.start_session()
    candidate = json.loads(builder.candidate_json)
    candidate["sections"][0]["blocks"][0]["claim_refs"] = ["invented-claim"]
    service.update_candidate(builder, candidate)

    with pytest.raises(MasterCvValidationError, match="unsupported claims"):
        service.approve_candidate()


def test_master_cv_summary_exposes_full_template_catalog(client):
    response = client.get("/master-cv/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["has_approved_profile"] is False
    assert len(payload["templates"]) == 13
    assert {item["id"] for item in payload["templates"]} >= {"swiss", "photo-corporate", "classic-ats"}
