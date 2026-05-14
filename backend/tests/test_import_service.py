from __future__ import annotations

import json

from sqlmodel import select

from backend.app.db.models import AuditLog, ImportedFile, Run, ValidationResult
from backend.app.imports.import_service import RunImportService
from backend.tests.conftest import copy_valid_run


def test_valid_import_persists_run_files_results_and_audit(db_session, runs_root):
    copy_valid_run(runs_root, "run-valid")

    result = RunImportService(db_session).import_run("run-valid")

    assert result.run.status == "imported"
    assert len(result.validation_results) == 9
    assert all(validation.status == "schema_validation_passed" for validation in result.validation_results)

    assert db_session.exec(select(Run)).one().run_id == "run-valid"
    assert len(db_session.exec(select(ImportedFile)).all()) == 9
    assert len(db_session.exec(select(ValidationResult)).all()) == 9
    audit_actions = [audit.action for audit in db_session.exec(select(AuditLog)).all()]
    assert "import_started" in audit_actions
    assert "file_validation_succeeded" in audit_actions
    assert "import_completed" in audit_actions


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
    assert len(db_session.exec(select(ImportedFile)).all()) == 9
    assert len(db_session.exec(select(ValidationResult)).all()) == 9
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
    assert len(db_session.exec(select(ImportedFile)).all()) == 9
    assert len(db_session.exec(select(ValidationResult)).all()) == 9

    failure_audit = db_session.exec(
        select(AuditLog).where(AuditLog.action == "import_failed", AuditLog.run_id == "run-crash").order_by(AuditLog.created_at.desc())
    ).first()
    assert failure_audit is not None
    assert json.loads(failure_audit.reason_codes_json) == ["import_exception"]
