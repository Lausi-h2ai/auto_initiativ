from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from backend.app.db.models import MasterCvBuilderSession, MasterCvDocumentSnapshot, ProfileAsset
from backend.app.master_cv.contracts import MasterCvDocument, PortraitCrop


def _document_payload() -> dict:
    return {
        "schema_version": "1.0",
        "document_snapshot_id": "master_cv_1",
        "profile_id": "profile_1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": "Primary CV",
        "locale": "de-CH",
        "portrait_asset_id": "portrait_1",
        "design": {
            "template_id": "swiss",
            "page_size": "A4",
            "page_count": 2,
            "density": "balanced",
            "accent_color": "#24364B",
            "photo": {"enabled": True, "shape": "rounded", "position": "header_right"},
        },
        "sections": [
            {
                "section_id": "experience",
                "type": "experience",
                "title": "Experience",
                "blocks": [
                    {
                        "block_id": "experience_1_bullet_1",
                        "kind": "bullet",
                        "text": "Led a documented program.",
                        "claim_refs": ["claim_123"],
                        "visible": True,
                    }
                ],
            }
        ],
    }


def test_master_cv_document_matches_pydantic_and_json_schema(schemas_root):
    payload = _document_payload()
    parsed = MasterCvDocument.model_validate(payload)
    schema = json.loads((schemas_root / "master_cv_document.schema.json").read_text(encoding="utf-8"))

    Draft202012Validator(schema).validate(payload)
    assert parsed.design.page_size == "A4"
    assert parsed.sections[0].blocks[0].claim_refs == ["claim_123"]


def test_master_cv_contract_rejects_raw_extra_content():
    payload = _document_payload()
    payload["raw_html"] = "<script>alert(1)</script>"

    with pytest.raises(ValidationError):
        MasterCvDocument.model_validate(payload)


def test_portrait_crop_must_stay_inside_normalized_bounds():
    with pytest.raises(ValidationError, match="within normalized image bounds"):
        PortraitCrop(x=0.8, y=0, width=0.3, height=1)


def test_master_cv_persistence_tables_are_registered():
    assert ProfileAsset.__tablename__ == "profile_assets"
    assert MasterCvDocumentSnapshot.__tablename__ == "master_cv_document_snapshots"
    assert MasterCvBuilderSession.__tablename__ == "master_cv_builder_sessions"
