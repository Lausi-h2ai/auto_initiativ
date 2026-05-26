from __future__ import annotations

import json
from datetime import datetime

from sqlmodel import select

from backend.app.db.models import (
    AuditLog,
    Company,
    Contact,
    EmailDraft,
    FitEvaluation,
    ImportedFile,
    ImportedGateResult,
    MasterCvProfileSnapshot,
    OutreachRecord,
    PolicySnapshot,
    SendIntent,
    SendReservation,
    UserProfileSnapshot,
)
from backend.app.imports.import_service import RunImportService
from backend.tests.conftest import copy_valid_run


def _rewrite_json(path, mutator) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    mutator(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_valid_import_normalizes_schema_valid_outputs_into_domain_tables(db_session, runs_root):
    copy_valid_run(runs_root, "run-valid-domain")

    result = RunImportService(db_session).import_run("run-valid-domain")

    assert result.run.status == "imported"
    assert len(db_session.exec(select(ImportedFile)).all()) == 10

    user_profile = db_session.exec(select(UserProfileSnapshot)).one()
    master_cv = db_session.exec(select(MasterCvProfileSnapshot)).one()
    policy = db_session.exec(select(PolicySnapshot)).one()
    company = db_session.exec(select(Company)).one()
    contact = db_session.exec(select(Contact)).one()
    fit_evaluation = db_session.exec(select(FitEvaluation)).one()
    draft = db_session.exec(select(EmailDraft)).one()
    intent = db_session.exec(select(SendIntent)).one()
    gate_result = db_session.exec(select(ImportedGateResult)).one()

    assert user_profile.profile_id == "profile-1"
    assert master_cv.profile_id == "master-cv-1"
    assert policy.policy_id == "policy-1"
    assert user_profile.status == "candidate"
    assert master_cv.status == "candidate"
    assert policy.status == "candidate"
    assert company.normalized_domain == "example.com"
    assert company.company_policy_key == "domain:example.com"
    assert contact.company_id == company.id
    assert contact.normalized_recipient_email == "alex.hiring@example.com"
    assert fit_evaluation.company_id == company.id
    assert fit_evaluation.policy_snapshot_id == policy.id
    assert draft.contact_id == contact.id
    assert intent.run_id == "run-valid-domain"
    assert intent.company_id == company.id
    assert intent.contact_id == contact.id
    assert intent.email_draft_id == draft.id
    assert intent.policy_snapshot_id == policy.id
    assert intent.user_profile_snapshot_id == user_profile.id
    assert intent.master_cv_profile_snapshot_id == master_cv.id
    assert intent.status == "imported"
    assert gate_result.status == "passed_evaluate_only"
    assert gate_result.send_intent_id == intent.id

    audit = db_session.exec(
        select(AuditLog).where(AuditLog.action == "domain_normalization_completed")
    ).one()
    assert audit.result_status == "domain_normalized"
    assert json.loads(audit.reason_codes_json) == []


def test_invalid_import_does_not_create_domain_rows(db_session, runs_root):
    output_path = copy_valid_run(runs_root, "run-invalid-domain")
    _rewrite_json(
        output_path / "contact_candidate.json",
        lambda data: data.update({"email": "not-an-email"}),
    )

    result = RunImportService(db_session).import_run("run-invalid-domain")

    assert result.run.status == "imported_with_errors"
    assert db_session.exec(select(UserProfileSnapshot)).all() == []
    assert db_session.exec(select(Company)).all() == []
    assert db_session.exec(select(SendIntent)).all() == []
    assert db_session.exec(select(ImportedGateResult)).all() == []
    assert db_session.exec(select(AuditLog).where(AuditLog.action == "domain_normalization_completed")).all() == []


def test_schema_valid_unresolved_references_mark_domain_rows_for_review(db_session, runs_root):
    output_path = copy_valid_run(runs_root, "run-unresolved-domain")
    _rewrite_json(
        output_path / "send_intent.json",
        lambda data: data.update({"contact_id": "missing-contact"}),
    )

    result = RunImportService(db_session).import_run("run-unresolved-domain")

    assert result.run.status == "imported_with_errors"
    intent = db_session.exec(select(SendIntent)).one()
    assert intent.contact_id is None
    assert intent.external_contact_id == "missing-contact"
    assert intent.status == "needs_review"

    audit = db_session.exec(
        select(AuditLog).where(AuditLog.action == "domain_normalization_completed")
    ).one()
    assert audit.result_status == "domain_normalized_with_review"
    assert json.loads(audit.reason_codes_json) == ["unresolved_references_present"]


def test_reimport_replaces_prior_domain_rows_for_same_run(db_session, runs_root):
    output_path = copy_valid_run(runs_root, "run-reimport-domain")
    service = RunImportService(db_session)

    first = service.import_run("run-reimport-domain")
    assert first.run.status == "imported"
    assert db_session.exec(select(Company)).one().normalized_domain == "example.com"

    _rewrite_json(
        output_path / "company_candidate.json",
        lambda data: data.update({"domain": "https://www.second-example.test/careers"}),
    )
    second = service.import_run("run-reimport-domain")

    assert second.run.status == "imported"
    companies = db_session.exec(select(Company)).all()
    intents = db_session.exec(select(SendIntent)).all()
    assert len(companies) == 1
    assert len(intents) == 1
    assert companies[0].normalized_domain == "second-example.test"
    assert companies[0].company_policy_key == "domain:second-example.test"


def test_reimport_clears_generated_evaluate_only_gate_results(db_session, runs_root):
    copy_valid_run(runs_root, "run-reimport-gate")
    service = RunImportService(db_session)
    service.import_run("run-reimport-gate")

    gate_result = ImportedGateResult(
        gate_result_id="gate-evaluate-only-intent-1",
        external_intent_id="intent-1",
        status="passed_evaluate_only",
        checks_json="[]",
        reasons_json="[]",
        evaluated_at=datetime.now(),
        imported_file_id=None,
    )
    db_session.add(gate_result)
    db_session.commit()

    service.import_run("run-reimport-gate")

    assert db_session.exec(
        select(ImportedGateResult).where(ImportedGateResult.gate_result_id == "gate-evaluate-only-intent-1")
    ).all() == []


def test_domain_normalization_does_not_create_send_state(db_session, runs_root):
    copy_valid_run(runs_root, "run-domain-boundary")

    result = RunImportService(db_session).import_run("run-domain-boundary")

    assert result.run.status == "imported"
    assert db_session.exec(select(SendReservation)).all() == []
    assert db_session.exec(select(OutreachRecord)).all() == []
