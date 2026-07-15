from __future__ import annotations

import json

from sqlmodel import select

from backend.app.db.models import AuditLog, ImportedFile, MasterCvProfileSnapshot, PolicySnapshot, Run, UserProfileSnapshot, ValidationResult
from backend.app.imports.import_service import RunImportService
from backend.tests.conftest import copy_valid_run


def _valid_user_profile_payload() -> dict[str, object]:
    provenance = {
        "source_type": "user_claim",
        "confidence": 0.9,
        "needs_review": False,
        "source_refs": ["onboarding_chat"],
    }
    return {
        "schema_version": "1.0",
        "profile_id": "profile-onboarding-only",
        "created_at": "2026-05-15T00:00:00+00:00",
        "identity": {"display_name": "Example User"},
        "preferences": {
            "target_roles": [{"value": "Backend engineer", "provenance": provenance}],
            "target_locations": [{"value": "Berlin", "provenance": provenance}],
            "remote_preferences": ["remote"],
            "communication_tone": {"value": "direct", "provenance": provenance},
        },
        "provenance_summary": {
            "source_documents": [],
            "interview_notes": ["Captured during onboarding chat."],
        },
    }


def _valid_master_cv_profile_payload() -> dict[str, object]:
    provenance = {
        "source_type": "user_claim",
        "confidence": 0.9,
        "needs_review": False,
        "source_refs": ["onboarding_chat"],
    }
    return {
        "schema_version": "1.0",
        "profile_id": "profile-onboarding-only",
        "created_at": "2026-05-15T00:00:00+00:00",
        "claims": [
            {
                "claim_id": "claim-onboarding-only-backend",
                "category": "skill",
                "statement": "Example User is targeting backend engineering roles.",
                "provenance": provenance,
                "approved_for_tailoring": False,
            }
        ],
    }


def _valid_policy_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "policy_id": "policy-onboarding-only",
        "created_at": "2026-05-15T00:00:00+00:00",
        "exclusions": {"industries": [], "company_names": [], "domains": [], "keywords": []},
        "outreach": {
            "allow_company_repeat": False,
            "allow_recipient_repeat": False,
            "company_dedupe_window_days": 365,
            "recipient_dedupe_window_days": 365,
            "require_manual_review_before_send": True,
        },
        "limits": {"daily_send_limit": 0, "weekly_send_limit": 0},
        "review_thresholds": {"minimum_required_confidence": 0.8, "block_needs_review_required_fields": True},
    }


def _valid_onboarding_review_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "review_id": "review-run-onboarding-chat",
        "run_id": "run-onboarding-chat",
        "created_at": "2026-05-15T00:00:00+00:00",
        "items": [],
    }


def _valid_email_draft_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "draft_id": "draft-run-application-draft",
        "company_id": "company-1",
        "contact_id": "contact-1",
        "subject": "Application",
        "body_text": "Hello",
        "claim_refs": ["claim-1"],
        "source_refs": ["source-1"],
        "attachments": [{"attachment_id": "cv-company-1", "path": "attachments/company-1-lebenslauf.pdf", "kind": "cv"}],
        "confidence": 0.9,
        "review_flags": [],
    }


def test_valid_import_persists_run_files_results_and_audit(db_session, runs_root):
    copy_valid_run(runs_root, "run-valid")

    result = RunImportService(db_session).import_run("run-valid")

    assert result.run.status == "imported"
    assert len(result.validation_results) == 10
    assert all(validation.status == "schema_validation_passed" for validation in result.validation_results)

    assert db_session.exec(select(Run)).one().run_id == "run-valid"
    assert len(db_session.exec(select(ImportedFile)).all()) == 10
    assert len(db_session.exec(select(ValidationResult)).all()) == 10
    audit_actions = [audit.action for audit in db_session.exec(select(AuditLog)).all()]
    assert "import_started" in audit_actions
    assert "file_validation_succeeded" in audit_actions
    assert "import_completed" in audit_actions


def test_onboarding_chat_import_validates_profile_artifacts_as_candidates(db_session, runs_root):
    output_path = runs_root / "run-onboarding-chat" / "output"
    output_path.mkdir(parents=True, exist_ok=True)
    (output_path / "user_profile.json").write_text(json.dumps(_valid_user_profile_payload()), encoding="utf-8")
    (output_path / "master_cv_profile.json").write_text(json.dumps(_valid_master_cv_profile_payload()), encoding="utf-8")
    (output_path / "policy.json").write_text(json.dumps(_valid_policy_payload()), encoding="utf-8")
    (output_path / "onboarding_review.json").write_text(json.dumps(_valid_onboarding_review_payload()), encoding="utf-8")

    result = RunImportService(db_session).import_run("run-onboarding-chat", run_type="onboarding_chat")

    assert result.run.status == "imported"
    assert result.run.agent_type == "onboarding_chat"
    assert {validation.filename for validation in result.validation_results} == {
        "user_profile.json",
        "master_cv_profile.json",
        "policy.json",
        "onboarding_review.json",
    }
    snapshot = db_session.exec(select(UserProfileSnapshot)).one()
    assert snapshot.profile_id == "profile-onboarding-only"
    assert snapshot.status == "candidate"
    assert db_session.exec(select(MasterCvProfileSnapshot)).one().status == "candidate"
    assert db_session.exec(select(PolicySnapshot)).one().status == "candidate"


def test_company_research_import_ignores_non_research_outputs(db_session, runs_root):
    copy_valid_run(runs_root, "run-company-research-safe")

    result = RunImportService(db_session).import_run("run-company-research-safe", run_type="company_research")

    assert result.run.status == "imported_with_errors"
    assert {validation.filename for validation in result.validation_results} == {
        "company_candidate.json",
        "contact_candidate.json",
        "fit_evaluation.json",
    }
    assert db_session.exec(select(UserProfileSnapshot)).all() == []


def test_incremental_research_import_does_not_duplicate_unchanged_files(db_session, runs_root):
    copy_valid_run(runs_root, "run-company-research-incremental")
    service = RunImportService(db_session)

    first = service.import_run(
        "run-company-research-incremental",
        run_type="company_research",
        incremental=True,
    )
    imported_file_count = len(
        db_session.exec(
            select(ImportedFile).where(ImportedFile.run_id == "run-company-research-incremental")
        ).all()
    )
    second = service.import_run(
        "run-company-research-incremental",
        run_type="company_research",
        incremental=True,
    )

    assert len(second.validation_results) == len(first.validation_results)
    assert len(
        db_session.exec(
            select(ImportedFile).where(ImportedFile.run_id == "run-company-research-incremental")
        ).all()
    ) == imported_file_count


def test_application_draft_import_validates_expected_resume_artifacts(db_session, runs_root):
    run_id = "run-application-draft"
    run_path = runs_root / run_id
    output_path = run_path / "output"
    attachments_path = output_path / "attachments"
    attachments_path.mkdir(parents=True, exist_ok=True)
    (run_path / "manifest.json").write_text(
        json.dumps(
            {
                "expected_output_files": [
                    "email_draft.json",
                    "attachments/company-1-lebenslauf.html",
                    "attachments/company-1-lebenslauf.pdf",
                ]
            }
        ),
        encoding="utf-8",
    )
    (output_path / "email_draft.json").write_text(json.dumps(_valid_email_draft_payload()), encoding="utf-8")
    (attachments_path / "company-1-lebenslauf.pdf").write_bytes(b"%PDF-" + (b"0" * 10_000))

    result = RunImportService(db_session).import_run(run_id, run_type="application_draft")

    assert result.run.status == "imported_with_errors"
    statuses = {validation.filename: validation.status for validation in result.validation_results}
    assert statuses["email_draft.json"] == "schema_validation_passed"
    assert statuses["attachments/company-1-lebenslauf.pdf"] == "artifact_validation_passed"
    assert statuses["attachments/company-1-lebenslauf.html"] == "missing_expected_file"


def test_invalid_json_import_records_clear_error(db_session, runs_root):
    output_path = copy_valid_run(runs_root, "run-invalid-json")
    (output_path / "company_candidate.json").write_text("{bad-json", encoding="utf-8")

    result = RunImportService(db_session).import_run("run-invalid-json")

    assert result.run.status == "imported_with_errors"
    invalid_result = next(item for item in result.validation_results if item.filename == "company_candidate.json")
    assert invalid_result.status == "invalid_json"
    assert json.loads(invalid_result.reason_codes_json) == ["invalid_json"]
    assert json.loads(invalid_result.errors_json)[0]["reason_code"] == "invalid_json"


def test_schema_mismatch_import_records_machine_readable_errors(db_session, runs_root):
    output_path = copy_valid_run(runs_root, "run-schema-mismatch")
    contact_path = output_path / "contact_candidate.json"
    contact = json.loads(contact_path.read_text(encoding="utf-8"))
    contact["email"] = "not-an-email"
    contact["email_source"] = "guessed"
    contact["confidence"] = -0.1
    contact["extra"] = "not allowed"
    contact_path.write_text(json.dumps(contact), encoding="utf-8")

    result = RunImportService(db_session).import_run("run-schema-mismatch")

    mismatch = next(item for item in result.validation_results if item.filename == "contact_candidate.json")
    reason_codes = set(json.loads(mismatch.reason_codes_json))
    assert result.run.status == "imported_with_errors"
    assert mismatch.status == "schema_validation_failed"
    assert {"additional_property", "invalid_email", "invalid_enum", "invalid_range"}.issubset(reason_codes)


def test_missing_expected_file_is_recorded_as_failed_validation(db_session, runs_root):
    output_path = copy_valid_run(runs_root, "run-missing-file")
    (output_path / "email_draft.json").unlink()

    result = RunImportService(db_session).import_run("run-missing-file")

    missing = next(item for item in result.validation_results if item.filename == "email_draft.json")
    assert result.run.status == "imported_with_errors"
    assert missing.status == "missing_expected_file"
    assert json.loads(missing.reason_codes_json) == ["missing_expected_file"]


def test_missing_output_directory_marks_run_import_failed(db_session):
    result = RunImportService(db_session).import_run("missing-output")

    assert result.run.status == "import_failed"
    assert result.validation_results == []
    audit = db_session.exec(select(AuditLog).where(AuditLog.action == "import_failed")).one()
    assert json.loads(audit.reason_codes_json) == ["missing_output_directory"]


def test_unknown_json_file_is_recorded(db_session, runs_root):
    output_path = copy_valid_run(runs_root, "run-unknown-file")
    (output_path / "notes.json").write_text("{}", encoding="utf-8")

    result = RunImportService(db_session).import_run("run-unknown-file")

    unknown = next(item for item in result.validation_results if item.filename == "notes.json")
    assert result.run.status == "imported_with_errors"
    assert unknown.status == "unknown_file_type"
    assert json.loads(unknown.reason_codes_json) == ["unknown_file_type"]


def test_unsupported_run_type_is_audited_without_importing_files(db_session, runs_root):
    copy_valid_run(runs_root, "run-unsupported-type")

    result = RunImportService(db_session).import_run("run-unsupported-type", run_type="send_intent")

    assert result.run.status == "import_failed"
    assert result.run.agent_type == "send_intent"
    assert result.validation_results == []
    assert db_session.exec(select(ImportedFile)).all() == []
    assert db_session.exec(select(ValidationResult)).all() == []

    failure_audit = db_session.exec(select(AuditLog).where(AuditLog.action == "import_failed")).one()
    assert json.loads(failure_audit.reason_codes_json) == ["unsupported_run_type"]
    assert json.loads(failure_audit.metadata_json)["run_type"] == "send_intent"


def test_reimport_replaces_prior_file_and_validation_rows(db_session, runs_root):
    output_path = copy_valid_run(runs_root, "run-reimport")
    service = RunImportService(db_session)

    first = service.import_run("run-reimport")
    (output_path / "company_candidate.json").write_text("{bad-json", encoding="utf-8")
    second = service.import_run("run-reimport")

    assert first.run.id == second.run.id
    assert len(db_session.exec(select(ImportedFile)).all()) == 10
    assert len(db_session.exec(select(ValidationResult)).all()) == 10
    assert second.run.status == "imported_with_errors"


def test_unexpected_import_exception_is_audited_and_preserves_prior_rows(db_session, runs_root):
    copy_valid_run(runs_root, "run-crash")
    service = RunImportService(db_session)
    service.import_run("run-crash")

    class ExplodingValidator:
        def validate_file(self, path):
            raise RuntimeError("validator exploded")

    result = RunImportService(db_session, validator=ExplodingValidator()).import_run("run-crash")

    assert result.run.status == "import_failed"
    assert result.validation_results == []
    assert len(db_session.exec(select(ImportedFile)).all()) == 10
    assert len(db_session.exec(select(ValidationResult)).all()) == 10

    failure_audit = db_session.exec(
        select(AuditLog).where(AuditLog.action == "import_failed", AuditLog.run_id == "run-crash").order_by(AuditLog.created_at.desc())
    ).first()
    assert failure_audit is not None
    assert json.loads(failure_audit.reason_codes_json) == ["import_exception"]
