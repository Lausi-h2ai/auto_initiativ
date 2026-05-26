from __future__ import annotations

import json

import pytest
from sqlmodel import select

from backend.app.db.models import AuditLog, Company, ImportedGateResult, OutreachRecord, SendIntent, SendReservation
from backend.app.email_delivery import EmailHandoffPreconditionError, EmailHandoffService, FakeDryRunEmailAdapter
from backend.app.gates.evaluate_only import EvaluateOnlyGateService
from backend.app.imports.import_service import RunImportService
from backend.app.onboarding.promotion import OnboardingPromotionService, SnapshotPromotionRequest
from backend.tests.conftest import copy_valid_run


def _promotion_request() -> SnapshotPromotionRequest:
    return SnapshotPromotionRequest(
        reviewer_id="test-reviewer",
        confirm_user_profile=True,
        confirm_master_cv_profile=True,
        confirm_policy=True,
    )


def _import_approved_run(db_session, runs_root, run_id: str = "adapter-valid") -> None:
    copy_valid_run(runs_root, run_id)
    result = RunImportService(db_session).import_run(run_id)
    assert result.run.status == "imported"
    promotion = OnboardingPromotionService(db_session).promote_run_snapshots(run_id, _promotion_request())
    assert promotion.status == "approved"
    db_session.commit()


def _intent(db_session) -> SendIntent:
    return db_session.exec(select(SendIntent).where(SendIntent.intent_id == "intent-1")).one()


def _company(db_session) -> Company:
    return db_session.exec(select(Company).where(Company.company_id == "company-1")).one()


class _ForbiddenAdapter(FakeDryRunEmailAdapter):
    provider = "forbidden_network_adapter"


class _FailingFakeAdapter(FakeDryRunEmailAdapter):
    def send(self, message):
        raise RuntimeError("fake adapter failure")


class _SpoofedFakeProviderAdapter:
    provider = "fake_dry_run"

    def __init__(self) -> None:
        self.messages = []

    def send(self, message):
        self.messages.append(message)
        raise AssertionError("spoofed fake provider should not be called")


def _reserve_gate_result(db_session) -> ImportedGateResult:
    evaluation = EvaluateOnlyGateService(db_session).evaluate("intent-1")
    assert evaluation.gate_result.status == "passed_evaluate_only"
    intent = _intent(db_session)
    company = _company(db_session)
    reservation = SendReservation(
        reservation_id="reservation-1",
        send_intent_id=intent.id,
        normalized_recipient_email=intent.normalized_recipient_email,
        company_id=company.id,
        company_policy_key=company.company_policy_key,
        policy_snapshot_id=intent.policy_snapshot_id,
        status="reserved",
    )
    db_session.add(reservation)
    evaluation.gate_result.status = "reserved_for_send"
    evaluation.gate_result.external_reservation_id = reservation.reservation_id
    evaluation.gate_result.reasons_json = "[]"
    raw = json.loads(evaluation.gate_result.raw_json)
    raw["status"] = "reserved_for_send"
    raw["reservation_id"] = reservation.reservation_id
    evaluation.gate_result.raw_json = json.dumps(raw)
    db_session.add(evaluation.gate_result)
    db_session.commit()
    return evaluation.gate_result


def test_fake_adapter_handoff_requires_reserved_gate(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    evaluation = EvaluateOnlyGateService(db_session).evaluate("intent-1")
    db_session.commit()
    adapter = FakeDryRunEmailAdapter()

    with pytest.raises(EmailHandoffPreconditionError) as exc_info:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(evaluation.gate_result.gate_result_id)

    assert exc_info.value.code == "reserved_gate_required"
    assert adapter.messages == []
    assert db_session.exec(select(OutreachRecord)).all() == []


def test_fake_adapter_handoff_requires_existing_gate_result(db_session):
    adapter = FakeDryRunEmailAdapter()

    with pytest.raises(EmailHandoffPreconditionError) as exc_info:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved("missing-gate-result")

    assert exc_info.value.code == "gate_result_missing"
    assert adapter.messages == []


@pytest.mark.parametrize("status", ["blocked", "needs_review", "passed_evaluate_only"])
def test_fake_adapter_handoff_rejects_non_reserved_gate_statuses(db_session, runs_root, status):
    _import_approved_run(db_session, runs_root)
    evaluation = EvaluateOnlyGateService(db_session).evaluate("intent-1")
    evaluation.gate_result.status = status
    db_session.add(evaluation.gate_result)
    db_session.commit()
    adapter = FakeDryRunEmailAdapter()

    with pytest.raises(EmailHandoffPreconditionError) as exc_info:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(evaluation.gate_result.gate_result_id)

    assert exc_info.value.code == "reserved_gate_required"
    assert adapter.messages == []
    assert db_session.exec(select(OutreachRecord)).all() == []


def test_fake_adapter_handoff_requires_matching_reservation(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    gate_result = _reserve_gate_result(db_session)
    reservation = db_session.exec(select(SendReservation).where(SendReservation.reservation_id == "reservation-1")).one()
    reservation.normalized_recipient_email = "other@example.com"
    db_session.add(reservation)
    db_session.commit()
    adapter = FakeDryRunEmailAdapter()

    with pytest.raises(EmailHandoffPreconditionError) as exc_info:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)

    assert exc_info.value.code == "reservation_recipient_mismatch"
    assert adapter.messages == []
    assert db_session.exec(select(OutreachRecord)).all() == []


def test_fake_adapter_handoff_requires_reservation_id_on_reserved_gate(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    gate_result = _reserve_gate_result(db_session)
    gate_result.external_reservation_id = None
    db_session.add(gate_result)
    db_session.commit()
    adapter = FakeDryRunEmailAdapter()

    with pytest.raises(EmailHandoffPreconditionError) as exc_info:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)

    assert exc_info.value.code == "reservation_required"
    assert adapter.messages == []


def test_fake_adapter_handoff_requires_existing_reservation_row(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    gate_result = _reserve_gate_result(db_session)
    reservation = db_session.exec(select(SendReservation).where(SendReservation.reservation_id == "reservation-1")).one()
    db_session.delete(reservation)
    db_session.commit()
    adapter = FakeDryRunEmailAdapter()

    with pytest.raises(EmailHandoffPreconditionError) as exc_info:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)

    assert exc_info.value.code == "reservation_missing"
    assert adapter.messages == []


def test_fake_adapter_handoff_requires_active_reservation_status(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    gate_result = _reserve_gate_result(db_session)
    reservation = db_session.exec(select(SendReservation).where(SendReservation.reservation_id == "reservation-1")).one()
    reservation.status = "released"
    db_session.add(reservation)
    db_session.commit()
    adapter = FakeDryRunEmailAdapter()

    with pytest.raises(EmailHandoffPreconditionError) as exc_info:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)

    assert exc_info.value.code == "reservation_not_active"
    assert adapter.messages == []


def test_fake_adapter_handoff_rejects_reservation_intent_policy_and_company_mismatches(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    gate_result = _reserve_gate_result(db_session)
    reservation = db_session.exec(select(SendReservation).where(SendReservation.reservation_id == "reservation-1")).one()
    adapter = FakeDryRunEmailAdapter()

    reservation.send_intent_id = None
    db_session.add(reservation)
    db_session.commit()
    with pytest.raises(EmailHandoffPreconditionError) as intent_exc:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)
    assert intent_exc.value.code == "reservation_intent_mismatch"

    reservation.send_intent_id = _intent(db_session).id
    reservation.policy_snapshot_id = None
    db_session.add(reservation)
    db_session.commit()
    with pytest.raises(EmailHandoffPreconditionError) as policy_exc:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)
    assert policy_exc.value.code == "reservation_policy_mismatch"

    reservation.policy_snapshot_id = _intent(db_session).policy_snapshot_id
    reservation.company_policy_key = "domain:other.example"
    db_session.add(reservation)
    db_session.commit()
    with pytest.raises(EmailHandoffPreconditionError) as company_exc:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)
    assert company_exc.value.code == "reservation_company_mismatch"
    assert adapter.messages == []


def test_fake_adapter_handoff_rejects_reserved_gate_with_reasons(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    gate_result = _reserve_gate_result(db_session)
    gate_result.reasons_json = json.dumps([{"code": "still_bad", "message": "Reserved gate has a reason."}])
    db_session.add(gate_result)
    db_session.commit()
    adapter = FakeDryRunEmailAdapter()

    with pytest.raises(EmailHandoffPreconditionError) as exc_info:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)

    assert exc_info.value.code == "gate_reasons_present"
    assert adapter.messages == []


def test_email_handoff_rejects_non_fake_adapter_before_preconditions(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    gate_result = _reserve_gate_result(db_session)
    adapter = _ForbiddenAdapter()

    with pytest.raises(EmailHandoffPreconditionError) as exc_info:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)

    assert exc_info.value.code == "fake_adapter_required"
    assert adapter.messages == []


def test_email_handoff_rejects_spoofed_fake_provider_adapter(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    gate_result = _reserve_gate_result(db_session)
    adapter = _SpoofedFakeProviderAdapter()

    with pytest.raises(EmailHandoffPreconditionError) as exc_info:
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)

    assert exc_info.value.code == "fake_adapter_required"
    assert adapter.messages == []


def test_email_handoff_flushes_started_audit_and_records_fake_adapter_failure(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    gate_result = _reserve_gate_result(db_session)
    adapter = FakeDryRunEmailAdapter()

    def fail_send(message):
        raise RuntimeError("fake adapter failure")

    adapter.send = fail_send
    with pytest.raises(RuntimeError, match="fake adapter failure"):
        EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)

    audit_actions = [audit.action for audit in db_session.exec(select(AuditLog)).all()]
    assert "email_adapter_handoff_started" in audit_actions
    assert "email_adapter_fake_failed" in audit_actions
    assert db_session.exec(select(OutreachRecord)).all() == []


def test_fake_adapter_handoff_records_dry_run_without_network_or_outreach(db_session, runs_root):
    _import_approved_run(db_session, runs_root)
    gate_result = _reserve_gate_result(db_session)
    adapter = FakeDryRunEmailAdapter()

    result = EmailHandoffService(db_session, adapter=adapter).handoff_reserved(gate_result.gate_result_id)
    db_session.commit()

    assert result.provider == "fake_dry_run"
    assert result.status == "dry_run_recorded"
    assert result.network_performed is False
    assert result.intent_id == "intent-1"
    assert result.provider_message_id == "fake-dry-run-intent-1"
    assert len(adapter.messages) == 1
    assert adapter.messages[0].recipient_email == "alex.hiring@example.com"
    assert db_session.exec(select(OutreachRecord)).all() == []

    audit_actions = [audit.action for audit in db_session.exec(select(AuditLog)).all()]
    assert "email_adapter_handoff_started" in audit_actions
    assert "email_adapter_fake_completed" in audit_actions
