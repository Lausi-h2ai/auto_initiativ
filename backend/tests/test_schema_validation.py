from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from backend.app.schemas.agent_outputs import AGENT_OUTPUT_MODELS
from backend.app.imports.file_classifier import EXPECTED_FILENAMES, classify_filename
from backend.app.imports.schema_registry import SchemaRegistry
from backend.app.imports.validation import JsonValidationService
from backend.tests.conftest import FIXTURES_ROOT


def test_schema_registry_loads_all_schemas(schemas_root):
    registry = SchemaRegistry(schemas_root=schemas_root)
    registry.load_all()

    assert len(registry.schema_names) == 12
    assert "onboarding_review.schema.json" in registry.schema_names
    assert "send_intent.schema.json" in registry.schema_names


def test_file_classifier_maps_expected_filenames():
    for filename in EXPECTED_FILENAMES:
        assert classify_filename(filename) is not None

    assert classify_filename("company_candidate.company-1.json") is None
    assert classify_filename("notes.json") is None


def test_validation_accepts_valid_fixture(schemas_root, tmp_path):
    fixture = tmp_path / "company_candidate.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "company_id": "company-1",
                "name": "Example",
                "domain": "example.com",
                "source_refs": ["source-1"],
                "confidence": 0.9,
                "review_flags": [],
            }
        ),
        encoding="utf-8",
    )

    outcome = JsonValidationService(SchemaRegistry(schemas_root=schemas_root)).validate_file(fixture)

    assert outcome.status == "schema_validation_passed"
    assert outcome.error_count == 0


def test_validation_rejects_invalid_json(schemas_root, tmp_path):
    fixture = tmp_path / "company_candidate.json"
    fixture.write_text("{not-json", encoding="utf-8")

    outcome = JsonValidationService(SchemaRegistry(schemas_root=schemas_root)).validate_file(fixture)

    assert outcome.status == "invalid_json"
    assert outcome.reason_codes == ["invalid_json"]
    assert outcome.errors[0]["line"] == 1


def test_validation_rejects_schema_mismatch_reasons(schemas_root, tmp_path):
    fixture = tmp_path / "contact_candidate.json"
    fixture.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "contact_id": "contact-1",
                "company_id": "company-1",
                "email": "not-an-email",
                "email_source": "unsupported_source",
                "confidence": 1.5,
                "source_refs": ["source-1"],
                "review_flags": [],
                "unexpected": True,
            }
        ),
        encoding="utf-8",
    )

    outcome = JsonValidationService(SchemaRegistry(schemas_root=schemas_root)).validate_file(fixture)

    assert outcome.status == "schema_validation_failed"
    assert {"additional_property", "invalid_email", "invalid_enum", "invalid_range"}.issubset(set(outcome.reason_codes))


def test_validation_rejects_unknown_json_filename(schemas_root, tmp_path):
    fixture = tmp_path / "unknown.json"
    fixture.write_text("{}", encoding="utf-8")

    outcome = JsonValidationService(SchemaRegistry(schemas_root=schemas_root)).validate_file(fixture)

    assert outcome.status == "unknown_file_type"
    assert outcome.reason_codes == ["unknown_file_type"]


@pytest.mark.parametrize("filename", EXPECTED_FILENAMES)
def test_valid_fixtures_match_pydantic_models(filename):
    schema_name = classify_filename(filename)
    assert schema_name is not None
    model = AGENT_OUTPUT_MODELS[schema_name]
    data = json.loads((FIXTURES_ROOT / "valid_run" / "output" / filename).read_text(encoding="utf-8"))

    model.model_validate(data)


@pytest.mark.parametrize("status", ["passed_evaluate_only", "blocked", "needs_review", "reserved_for_send"])
def test_gate_result_accepts_only_gate_statuses(schemas_root, tmp_path, status):
    data = json.loads((FIXTURES_ROOT / "valid_run" / "output" / "gate_result.json").read_text(encoding="utf-8"))
    data["status"] = status
    fixture = tmp_path / "gate_result.json"
    fixture.write_text(json.dumps(data), encoding="utf-8")

    outcome = JsonValidationService(SchemaRegistry(schemas_root=schemas_root)).validate_file(fixture)

    assert outcome.status == "schema_validation_passed"
    AGENT_OUTPUT_MODELS["gate_result.schema.json"].model_validate(data)


@pytest.mark.parametrize("status", ["passed_dry_run", "reserved", "sent", "send_failed"])
def test_gate_result_rejects_legacy_and_send_result_statuses(schemas_root, tmp_path, status):
    data = json.loads((FIXTURES_ROOT / "valid_run" / "output" / "gate_result.json").read_text(encoding="utf-8"))
    data["status"] = status
    fixture = tmp_path / "gate_result.json"
    fixture.write_text(json.dumps(data), encoding="utf-8")

    outcome = JsonValidationService(SchemaRegistry(schemas_root=schemas_root)).validate_file(fixture)

    assert outcome.status == "schema_validation_failed"
    assert "invalid_enum" in outcome.reason_codes
    with pytest.raises(ValidationError):
        AGENT_OUTPUT_MODELS["gate_result.schema.json"].model_validate(data)


@pytest.mark.parametrize(
    ("filename", "field_name"),
    [
        ("company_candidate.json", "website_url"),
        ("contact_candidate.json", "name"),
        ("email_draft.json", "body_html"),
        ("gate_result.json", "reservation_id"),
        ("master_cv_profile.json", "preferred_cv_sections"),
        ("policy.json", "forbidden_claims"),
        ("send_intent.json", "recipient_name"),
        ("user_profile.json", "updated_at"),
    ],
)
def test_explicit_null_optional_fields_are_rejected_by_schema_and_pydantic(schemas_root, tmp_path, filename, field_name):
    source_path = FIXTURES_ROOT / "valid_run" / "output" / filename
    data = json.loads(source_path.read_text(encoding="utf-8"))
    data[field_name] = None
    fixture = tmp_path / filename
    fixture.write_text(json.dumps(data), encoding="utf-8")

    outcome = JsonValidationService(SchemaRegistry(schemas_root=schemas_root)).validate_file(fixture)
    assert outcome.status == "schema_validation_failed"

    schema_name = classify_filename(filename)
    assert schema_name is not None
    with pytest.raises(ValidationError):
        AGENT_OUTPUT_MODELS[schema_name].model_validate(data)


def test_onboarding_review_rejects_hidden_side_effects(schemas_root, tmp_path):
    data = json.loads((FIXTURES_ROOT / "valid_run" / "output" / "onboarding_review.json").read_text(encoding="utf-8"))
    data["items"][0]["send_email"] = True
    fixture = tmp_path / "onboarding_review.json"
    fixture.write_text(json.dumps(data), encoding="utf-8")

    outcome = JsonValidationService(SchemaRegistry(schemas_root=schemas_root)).validate_file(fixture)

    assert outcome.status == "schema_validation_failed"
    assert "additional_property" in outcome.reason_codes
    with pytest.raises(ValidationError):
        AGENT_OUTPUT_MODELS["onboarding_review.schema.json"].model_validate(data)


def test_onboarding_review_rejects_explicit_null_optional_nested_fields(schemas_root, tmp_path):
    data = json.loads((FIXTURES_ROOT / "valid_run" / "output" / "onboarding_review.json").read_text(encoding="utf-8"))
    data["items"][0]["related_json_pointers"] = None
    fixture = tmp_path / "onboarding_review.json"
    fixture.write_text(json.dumps(data), encoding="utf-8")

    outcome = JsonValidationService(SchemaRegistry(schemas_root=schemas_root)).validate_file(fixture)

    assert outcome.status == "schema_validation_failed"
    with pytest.raises(ValidationError):
        AGENT_OUTPUT_MODELS["onboarding_review.schema.json"].model_validate(data)


@pytest.mark.parametrize("item_type", ["missing_required_information", "contradiction"])
def test_onboarding_review_has_first_class_review_item_types(item_type):
    data = json.loads((FIXTURES_ROOT / "valid_run" / "output" / "onboarding_review.json").read_text(encoding="utf-8"))
    data["items"][0]["item_type"] = item_type

    review = AGENT_OUTPUT_MODELS["onboarding_review.schema.json"].model_validate(data)

    assert review.items[0].item_type == item_type
