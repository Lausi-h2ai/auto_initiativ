from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pypdf import PdfReader
from sqlmodel import select

from backend.app.core.config import get_settings
from backend.app.db.models import Document, MasterCvBuilderSession, MasterCvProfileSnapshot
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


@pytest.mark.parametrize(
    ("template_id", "expected_style"),
    [
        ("classic-ats", "justify-content:center"),
        ("atelier", "border-left:8mm solid"),
        ("editorial-banner", "grid-template-columns:1fr 1fr 1fr"),
        ("elegant-serif", "Palatino Linotype"),
        ("executive", "border-top:7mm solid"),
        ("ledger", "Courier New"),
        ("modern-sidebar", "linear-gradient(90deg"),
        ("photo-corporate", "border-radius:50%"),
        ("photo-minimal", "flex-direction:row-reverse"),
        ("pillar", "grid-template-columns:1fr 1fr"),
        ("swiss", "display:contents"),
        ("tech-compact", "grid-template-columns:1.25fr .75fr"),
        ("timeline", "border-left:3px solid"),
    ],
)
def test_renderer_applies_a_distinct_safe_adapter_for_every_template(template_id, expected_style):
    payload = {
        "schema_version": "1.0", "document_snapshot_id": f"snapshot-{template_id}",
        "profile_id": "profile_test", "created_at": datetime.now(timezone.utc).isoformat(),
        "title": "Master Lebenslauf", "locale": "de-CH",
        "design": {"template_id": template_id, "page_size": "A4", "page_count": 1, "density": "balanced"},
        "sections": [{
            "section_id": "experience", "type": "experience", "title": "Berufserfahrung",
            "blocks": [{"block_id": "claim-1", "kind": "entry", "text": "Approved experience.", "claim_refs": ["claim-1"], "visible": True}],
        }],
    }

    html = render_master_cv_html(MasterCvDocument.model_validate(payload))

    assert f"master-cv-template-{template_id}" in html
    assert expected_style in html
    assert 'lang="de-CH"' in html
    assert "overflow-x:hidden" in html


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
    assert len(documents) == 2
    assert {item.mime_type for item in documents} == {"text/html", "application/pdf"}
    pdf_document = next(item for item in documents if item.mime_type == "application/pdf")
    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(runs_root / pdf_document.relative_path).pages)
    assert "Led a documented transformation program." in pdf_text
    assert (runs_root / documents[0].relative_path).exists()
    downstream_html = approved_master_cv_html(db_session, settings)
    assert 'data-master-cv-template="classic-ats"' in downstream_html
    assert "Led a documented transformation program." in downstream_html


def test_agent_candidate_import_normalizes_legacy_catalog_density(db_session, runs_root):
    profile = _profile()
    db_session.add(MasterCvProfileSnapshot(
        profile_id=profile["profile_id"], schema_version="1.0", content_hash="profile-density-hash",
        status="approved", raw_json=json.dumps(profile), source_created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()
    service = MasterCvService(session=db_session, settings=get_settings())
    builder = service.start_session()
    payload = json.loads(builder.candidate_json)
    payload["design"]["density"] = "comfortable"
    output = runs_root / builder.run_id / "output"
    output.mkdir(parents=True, exist_ok=True)
    (output / "master_cv_document.json").write_text(json.dumps(payload), encoding="utf-8")

    imported = service.import_agent_candidate(builder)

    assert imported is not None
    assert imported.design.density == "balanced"
    assert json.loads(builder.candidate_json)["design"]["density"] == "balanced"


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


def test_candidate_is_durable_versioned_and_rejects_stale_or_unreviewed_direct_edits(db_session):
    profile = _profile()
    db_session.add(MasterCvProfileSnapshot(
        profile_id=profile["profile_id"], schema_version="1.0", content_hash="profile-hash-durable",
        status="approved", raw_json=json.dumps(profile), source_created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()
    service = MasterCvService(session=db_session, settings=get_settings())
    builder = service.start_session()
    candidate = json.loads(builder.candidate_json)
    durable = service.candidate(candidate["document_snapshot_id"])

    assert durable is not None
    assert durable.status == "candidate"
    assert durable.version_number == 1

    updated = service.patch_design({"template_id": "swiss", "expected_revision": candidate["revision"]})
    assert updated.revision == candidate["revision"] + 1
    with pytest.raises(MasterCvValidationError, match="Stale candidate revision"):
        service.patch_design({"template_id": "atelier", "expected_revision": candidate["revision"]})

    edited = service.patch_block(
        updated.sections[0].blocks[0].block_id,
        {"text": "A materially different unsupported assertion.", "expected_revision": updated.revision},
    )
    assert edited.lifecycle_status == "needs_review"
    assert edited.sections[0].blocks[0].claim_refs == []
    assert edited.sections[0].blocks[0].metadata["needs_review"] is True
    with pytest.raises(MasterCvValidationError, match="review"):
        service.approve_candidate()


def test_downstream_resolver_preserves_an_explicit_campaign_pin(db_session):
    profile = _profile()
    db_session.add(MasterCvProfileSnapshot(
        profile_id=profile["profile_id"], schema_version="1.0", content_hash="profile-hash-pin",
        status="approved", raw_json=json.dumps(profile), source_created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()
    settings = get_settings()
    service = MasterCvService(session=db_session, settings=settings)

    service.start_session()
    first = service.approve_candidate()
    second_builder = service.start_session()
    second_payload = json.loads(second_builder.candidate_json)
    service.patch_design({"template_id": "swiss", "expected_revision": second_payload["revision"]})
    second = service.approve_candidate()

    assert 'data-master-cv-template="swiss"' in approved_master_cv_html(db_session, settings)
    assert 'data-master-cv-template="classic-ats"' in approved_master_cv_html(
        db_session, settings, document_snapshot_id=first.id,
    )
    assert second.id != first.id


def test_template_change_materializes_a_legacy_session_only_candidate(db_session):
    profile = _profile()
    db_session.add(MasterCvProfileSnapshot(
        profile_id=profile["profile_id"], schema_version="1.0", content_hash="profile-hash-legacy",
        status="approved", raw_json=json.dumps(profile), source_created_at=datetime.now(timezone.utc),
    ))
    db_session.commit()
    service = MasterCvService(session=db_session, settings=get_settings())
    candidate = service._default_candidate(profile)
    candidate.pop("revision", None)
    legacy = MasterCvBuilderSession(
        session_id="legacy-master-cv-session", run_id="legacy-master-cv-run",
        candidate_json=json.dumps(candidate), status="active",
    )
    db_session.add(legacy)
    db_session.commit()

    updated = service.patch_design({"template_id": "swiss"})

    assert updated.design.template_id == "swiss"
    assert updated.revision == 2
    assert legacy.current_candidate_snapshot_id is not None
    durable = service.candidate(updated.document_snapshot_id)
    assert durable is not None
    assert durable.status == "candidate"
    assert durable.template_id == "swiss"


def test_master_cv_summary_exposes_full_template_catalog(client):
    response = client.get("/master-cv/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["has_approved_profile"] is False
    assert len(payload["templates"]) == 13
    assert {item["id"] for item in payload["templates"]} >= {"swiss", "photo-corporate", "classic-ats"}
