from __future__ import annotations

import json

import pytest
from sqlmodel import select

from backend.app.db.models import (
    AuditLog,
    Company,
    Contact,
    EmailDraft,
    FitEvaluation,
    ImportedGateResult,
    OutreachRecord,
    PolicySnapshot,
    SendIntent,
    SendReservation,
)
from backend.app.gates.evaluate_only import EvaluateOnlyGateService
from backend.app.imports.import_service import RunImportService
from backend.app.onboarding.promotion import OnboardingPromotionService, SnapshotPromotionRequest
from backend.app.schemas.agent_outputs import AGENT_OUTPUT_MODELS
from backend.tests.conftest import copy_valid_run


def _import_valid_run(db_session, runs_root, run_id: str = "gate-valid") -> None:
    copy_valid_run(runs_root, run_id)
    result = RunImportService(db_session).import_run(run_id)
    assert result.run.status == "imported"
    promotion = OnboardingPromotionService(db_session).promote_run_snapshots(run_id, _promotion_request())
    assert promotion.status == "approved"
    db_session.commit()


def _import_candidate_run(db_session, runs_root, run_id: str = "gate-valid") -> None:
    copy_valid_run(runs_root, run_id)
    result = RunImportService(db_session).import_run(run_id)
    assert result.run.status == "imported"


def _promotion_request() -> SnapshotPromotionRequest:
    return SnapshotPromotionRequest(
        reviewer_id="test-reviewer",
        confirm_user_profile=True,
        confirm_master_cv_profile=True,
        confirm_policy=True,
    )


def _evaluate(db_session, intent_id: str = "intent-1"):
    result = EvaluateOnlyGateService(db_session).evaluate(intent_id)
    db_session.commit()
    return result


def _intent(db_session) -> SendIntent:
    return db_session.exec(select(SendIntent).where(SendIntent.intent_id == "intent-1")).one()


def _policy(db_session) -> PolicySnapshot:
    return db_session.exec(select(PolicySnapshot).where(PolicySnapshot.policy_id == "policy-1")).one()


def _company(db_session) -> Company:
    return db_session.exec(select(Company).where(Company.company_id == "company-1")).one()


def _contact(db_session) -> Contact:
    return db_session.exec(select(Contact).where(Contact.contact_id == "contact-1")).one()


def _email_draft(db_session) -> EmailDraft:
    return db_session.exec(select(EmailDraft).where(EmailDraft.draft_id == "draft-1")).one()


def _fit_evaluation(db_session) -> FitEvaluation:
    return db_session.exec(select(FitEvaluation).where(FitEvaluation.evaluation_id == "evaluation-1")).one()


def _reason_codes(result) -> set[str]:
    return {reason["code"] for reason in result.reasons}


def _check_codes(result) -> set[str]:
    return {check["code"] for check in result.checks}


def _rewrite_policy(db_session, mutator) -> None:
    policy = _policy(db_session)
    data = json.loads(policy.raw_json)
    mutator(data)
    policy.raw_json = json.dumps(data)
    db_session.add(policy)
    db_session.commit()


def _rewrite_intent_raw(db_session, mutator) -> None:
    send_intent = _intent(db_session)
    raw_json = json.loads(send_intent.raw_json)
    mutator(raw_json)
    send_intent.raw_json = json.dumps(raw_json)
    db_session.add(send_intent)
    db_session.commit()


def test_evaluate_only_gate_passes_valid_import_without_reservation(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    result = _evaluate(db_session)

    assert result.gate_result.status == "passed_evaluate_only"
    assert result.gate_result.gate_result_id == "gate-evaluate-only-intent-1"
    assert result.gate_result.imported_file_id is None
    assert not result.reasons
    assert all(check["status"] == "pass" for check in result.checks)
    AGENT_OUTPUT_MODELS["gate_result.schema.json"].model_validate(json.loads(result.gate_result.raw_json))

    assert db_session.exec(select(SendReservation)).all() == []
    audit_actions = [audit.action for audit in db_session.exec(select(AuditLog)).all()]
    assert "gate_evaluation_started" in audit_actions
    assert "gate_evaluation_completed" in audit_actions


def test_evaluate_only_gate_blocks_duplicate_recipient(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    db_session.add(
        OutreachRecord(
            outreach_record_id="outreach-existing",
            normalized_recipient_email="alex.hiring@example.com",
            company_policy_key="domain:other.example",
            status="sent",
        )
    )
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "duplicate_recipient" in _reason_codes(result)
    assert db_session.exec(select(SendReservation)).all() == []


def test_evaluate_only_gate_blocks_duplicate_company(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    db_session.add(
        OutreachRecord(
            outreach_record_id="outreach-existing-company",
            normalized_recipient_email="other@example.com",
            company_policy_key="domain:example.com",
            status="sent",
        )
    )
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "duplicate_company" in _reason_codes(result)
    assert db_session.exec(select(SendReservation)).all() == []


def test_evaluate_only_gate_allows_recipient_repeat_when_policy_allows(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    def allow_recipient_repeat(policy):
        policy["outreach"]["allow_recipient_repeat"] = True

    _rewrite_policy(db_session, allow_recipient_repeat)
    db_session.add(
        OutreachRecord(
            outreach_record_id="outreach-existing-recipient",
            normalized_recipient_email="alex.hiring@example.com",
            company_policy_key="domain:other.example",
            status="sent",
        )
    )
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "passed_evaluate_only"
    assert "duplicate_recipient" not in _reason_codes(result)
    assert "recipient_repeat_allowed" in _check_codes(result)


def test_evaluate_only_gate_allows_company_repeat_when_policy_allows(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    def allow_company_repeat(policy):
        policy["outreach"]["allow_company_repeat"] = True

    _rewrite_policy(db_session, allow_company_repeat)
    db_session.add(
        OutreachRecord(
            outreach_record_id="outreach-existing-company",
            normalized_recipient_email="other@example.com",
            company_policy_key="domain:example.com",
            status="sent",
        )
    )
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "passed_evaluate_only"
    assert "duplicate_company" not in _reason_codes(result)
    assert "company_repeat_allowed" in _check_codes(result)


def test_evaluate_only_gate_blocks_schema_invalid_raw_intent(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    def remove_required(raw_json):
        del raw_json["recipient_email"]

    _rewrite_intent_raw(db_session, remove_required)

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "schema_missing_required_field" in _reason_codes(result)


def test_evaluate_only_gate_blocks_missing_raw_send_intent_json(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.raw_json = ""
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "schema_validity" in _reason_codes(result)


def test_evaluate_only_gate_blocks_malformed_raw_send_intent_json(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.raw_json = "{"
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "schema_invalid_json" in _reason_codes(result)
    completed_audit = db_session.exec(
        select(AuditLog).where(AuditLog.action == "gate_evaluation_completed").order_by(AuditLog.created_at.desc())
    ).first()
    assert completed_audit is not None
    assert "schema_invalid_json" in json.loads(completed_audit.reason_codes_json)


@pytest.mark.parametrize(
    ("mutator", "reason_code"),
    [
        (lambda raw_json: raw_json.update({"extra": "not allowed"}), "schema_additional_property"),
        (lambda raw_json: raw_json.update({"created_by": "user"}), "schema_invalid_enum"),
        (lambda raw_json: raw_json.update({"recipient_email": "not-an-email"}), "schema_invalid_email"),
    ],
)
def test_evaluate_only_gate_blocks_schema_contract_violations(db_session, runs_root, mutator, reason_code):
    _import_valid_run(db_session, runs_root)
    _rewrite_intent_raw(db_session, mutator)

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert reason_code in _reason_codes(result)


def test_evaluate_only_gate_blocks_missing_policy_snapshot(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.policy_snapshot_id = None
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "policy_missing" in _reason_codes(result)


def test_evaluate_only_gate_blocks_policy_mismatch(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.external_policy_id = "other-policy"
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "policy_mismatch" in _reason_codes(result)


def test_evaluate_only_gate_blocks_candidate_snapshots(db_session, runs_root):
    _import_candidate_run(db_session, runs_root)

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "snapshot_not_approved" in _reason_codes(result)


@pytest.mark.parametrize(
    ("field_name", "reason_code"),
    [
        ("company_id", "required_record_missing"),
        ("contact_id", "required_record_missing"),
        ("email_draft_id", "required_record_missing"),
        ("user_profile_snapshot_id", "required_record_missing"),
        ("master_cv_profile_snapshot_id", "required_record_missing"),
    ],
)
def test_evaluate_only_gate_blocks_missing_linked_records(db_session, runs_root, field_name, reason_code):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    setattr(send_intent, field_name, None)
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert reason_code in _reason_codes(result)


def test_evaluate_only_gate_blocks_policy_blocked_domain(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    def block_domain(policy):
        policy["exclusions"]["domains"] = [
            {"value": "example.com", "reason": "blocked test domain", "provenance": _policy_item_provenance()}
        ]

    _rewrite_policy(db_session, block_domain)

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "blocked_domain" in _reason_codes(result)


def test_evaluate_only_gate_blocks_policy_blocked_company(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    def block_company(policy):
        policy["exclusions"]["company_names"] = [
            {"value": "Example Robotics", "reason": "blocked test company", "provenance": _policy_item_provenance()}
        ]

    _rewrite_policy(db_session, block_company)

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "blocked_company" in _reason_codes(result)


def test_evaluate_only_gate_blocks_policy_keyword(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    def block_keyword(policy):
        policy["exclusions"]["keywords"] = [
            {"value": "backend engineering", "reason": "blocked phrase", "provenance": _policy_item_provenance()}
        ]

    _rewrite_policy(db_session, block_keyword)

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "blocked_keyword" in _reason_codes(result)


def test_evaluate_only_gate_blocks_missing_source_refs(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.source_refs_json = "[]"
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "source_refs_missing" in _reason_codes(result)


def test_evaluate_only_gate_blocks_unresolved_draft_source_refs(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.source_refs_json = json.dumps(["source-not-on-draft"])
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "source_refs_not_in_draft" in _reason_codes(result)


def test_evaluate_only_gate_blocks_missing_attachment(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.attachments_json = json.dumps(
        [
            {
                "attachment_id": "attachment-missing",
                "path": "attachments/missing.pdf",
                "kind": "cv",
                "exists_at_draft_time": False,
            }
        ]
    )
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "attachments_missing" in _reason_codes(result)


def test_evaluate_only_gate_blocks_missing_send_limits(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    def remove_limits(policy):
        policy["limits"] = {}

    _rewrite_policy(db_session, remove_limits)

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "send_limits_missing" in _reason_codes(result)


@pytest.mark.parametrize(
    ("limit_name", "reason_code"),
    [("daily_send_limit", "daily_limit_reached"), ("weekly_send_limit", "weekly_limit_reached")],
)
def test_evaluate_only_gate_blocks_reached_send_limits(db_session, runs_root, limit_name, reason_code):
    _import_valid_run(db_session, runs_root)

    def set_limit(policy):
        policy["limits"]["daily_send_limit"] = 10
        policy["limits"]["weekly_send_limit"] = 10
        policy["limits"][limit_name] = 0

    _rewrite_policy(db_session, set_limit)

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert reason_code in _reason_codes(result)


def test_evaluate_only_gate_treats_unapproved_claim_reference_as_advisory(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    gate_result = db_session.exec(select(ImportedGateResult).where(ImportedGateResult.gate_result_id == "gate-1")).one()
    assert gate_result.imported_file_id is not None
    intent = gate_result.send_intent_id
    assert intent is not None

    send_intent = db_session.get(SendIntent, intent)
    assert send_intent is not None
    send_intent.claim_refs_json = json.dumps(["claim-not-approved"])
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "passed_evaluate_only"
    assert "unapproved_claim_refs" not in _reason_codes(result)
    assert "claim_refs_advisory" in _check_codes(result)


def test_evaluate_only_gate_blocks_forbidden_claim_text(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    def forbid_claim(policy):
        policy["forbidden_claims"] = ["backend engineering"]

    _rewrite_policy(db_session, forbid_claim)

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "forbidden_claim_present" in _reason_codes(result)


def test_evaluate_only_gate_blocks_low_confidence_required_field(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.confidence = 0.1
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "low_confidence_required_field" in _reason_codes(result)


def test_evaluate_only_gate_treats_moderate_confidence_as_advisory(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.confidence = 0.68
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "passed_evaluate_only"
    assert "low_confidence_required_field" not in _reason_codes(result)
    assert "confidence_threshold_advisory" in _check_codes(result)


@pytest.mark.parametrize("record_getter", [_company, _contact, _email_draft, _fit_evaluation])
def test_evaluate_only_gate_blocks_low_confidence_related_record(db_session, runs_root, record_getter):
    _import_valid_run(db_session, runs_root)
    record = record_getter(db_session)
    record.confidence = 0.1
    db_session.add(record)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "low_confidence_required_field" in _reason_codes(result)


def test_evaluate_only_gate_blocks_hard_review_flags_on_required_fields(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    contact = _contact(db_session)
    contact.review_flags_json = json.dumps(["policy_conflict_requires_resolution"])
    db_session.add(contact)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "review_flags_present" in _reason_codes(result)


@pytest.mark.parametrize("review_flag", ["generic_recipient", "remote_policy_unknown", "claim_id_references"])
def test_evaluate_only_gate_allows_nonblocking_review_flags(db_session, runs_root, review_flag):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.review_flags_json = json.dumps([review_flag])
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "passed_evaluate_only"
    assert "review_flags_present" not in _reason_codes(result)


@pytest.mark.parametrize(
    "review_flag",
    [
        "needs_review",
        "recipient_email_inferred_generic_needs_manual_verification",
        "language_may_need_english_review_due_english_first_company_site",
        "specific_open_roles_not_verified",
        "master_cv_profile_contains_no_structured_claim_ids",
    ],
)
def test_evaluate_only_gate_allows_agent_remediable_review_flags(db_session, runs_root, review_flag):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.review_flags_json = json.dumps([review_flag])
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "passed_evaluate_only"
    assert "review_flags_present" not in _reason_codes(result)


def test_evaluate_only_gate_treats_review_flags_as_advisory_when_policy_allows_review(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    def allow_review(policy):
        policy["review_thresholds"]["block_needs_review_required_fields"] = False

    _rewrite_policy(db_session, allow_review)
    send_intent = _intent(db_session)
    send_intent.review_flags_json = json.dumps(["needs_review"])
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "passed_evaluate_only"
    assert "review_flags_present" not in _reason_codes(result)
    assert "review_flags_advisory" in _check_codes(result)


def test_evaluate_only_gate_requires_confidence_threshold(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    def remove_threshold(policy):
        policy["review_thresholds"] = {}

    _rewrite_policy(db_session, remove_threshold)

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "confidence_threshold_missing" in _reason_codes(result)


def test_evaluate_only_gate_treats_inferred_contact_email_as_advisory(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    contact = _contact(db_session)
    contact.email_source = "inferred_pattern"
    db_session.add(contact)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "passed_evaluate_only"
    assert "contact_email_needs_review" not in _reason_codes(result)
    assert "contact_email_source_advisory" in _check_codes(result)


def test_evaluate_only_gate_treats_unknown_contact_email_source_as_advisory(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    contact = _contact(db_session)
    contact.email_source = "unknown"
    db_session.add(contact)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "passed_evaluate_only"
    assert "contact_email_source_unknown" not in _reason_codes(result)
    assert "contact_email_source_unknown_advisory" in _check_codes(result)


def test_evaluate_only_gate_blocks_when_failures_and_warnings_both_present(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    contact = _contact(db_session)
    contact.email_source = "inferred_pattern"
    db_session.add(contact)
    send_intent = _intent(db_session)
    send_intent.confidence = 0.1
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "low_confidence_required_field" in _reason_codes(result)
    assert "contact_email_needs_review" not in _reason_codes(result)


def test_evaluate_only_gate_writes_completed_audit_reason_codes(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    send_intent = _intent(db_session)
    send_intent.confidence = 0.1
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)
    completed_audit = db_session.exec(
        select(AuditLog).where(AuditLog.action == "gate_evaluation_completed").order_by(AuditLog.created_at.desc())
    ).first()

    assert completed_audit is not None
    assert json.loads(completed_audit.reason_codes_json) == [reason["code"] for reason in result.reasons]


def test_evaluate_only_gate_is_idempotent_for_same_intent(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    first = _evaluate(db_session)
    second = _evaluate(db_session)

    assert first.gate_result.gate_result_id == second.gate_result.gate_result_id
    assert first.gate_result.status == second.gate_result.status
    assert first.checks == second.checks
    assert first.reasons == second.reasons
    generated_results = db_session.exec(
        select(ImportedGateResult).where(ImportedGateResult.gate_result_id == "gate-evaluate-only-intent-1")
    ).all()
    assert len(generated_results) == 1


def test_evaluate_only_gate_api_exposes_gate_result_without_send_endpoint(client, runs_root):
    copy_valid_run(runs_root, "gate-api")
    import_response = client.post("/runs/gate-api/import")
    assert import_response.status_code == 200
    promotion_response = client.post(
        "/onboarding/runs/gate-api/promote",
        json={
            "reviewer_id": "test-reviewer",
            "confirm_user_profile": True,
            "confirm_master_cv_profile": True,
            "confirm_policy": True,
        },
    )
    assert promotion_response.status_code == 200
    assert promotion_response.json()["status"] == "approved"

    response = client.post("/gate/evaluations/intent-1")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed_evaluate_only"
    assert body["gate_result_id"] == "gate-evaluate-only-intent-1"

    openapi = client.get("/openapi.json").json()
    assert "/gate/evaluations/{intent_id}" in openapi["paths"]
    assert not any(path.lower() == "/send" for path in openapi["paths"])


def test_evaluate_only_gate_raises_for_missing_intent(db_session):
    with pytest.raises(ValueError, match="Send intent not found"):
        EvaluateOnlyGateService(db_session).evaluate("missing-intent")


def _policy_item_provenance() -> dict:
    return {
        "source_type": "user_claim",
        "confidence": 1.0,
        "needs_review": False,
        "source_refs": ["test-policy"],
    }
