from __future__ import annotations

import json

from sqlmodel import select

from backend.app.db.models import AuditLog, Company, ImportedGateResult, OutreachRecord, SendIntent, SendReservation
from backend.app.gates.reserve_for_send import ReserveForSendGateService
from backend.app.imports.import_service import RunImportService
from backend.app.onboarding.promotion import OnboardingPromotionService, SnapshotPromotionRequest
from backend.app.schemas.agent_outputs import AGENT_OUTPUT_MODELS
from backend.tests.conftest import copy_valid_run


def _promotion_request() -> SnapshotPromotionRequest:
    return SnapshotPromotionRequest(
        reviewer_id="test-reviewer",
        confirm_user_profile=True,
        confirm_master_cv_profile=True,
        confirm_policy=True,
    )


def _import_valid_run(db_session, runs_root, run_id: str = "reserve-valid") -> None:
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


def _reason_codes(result) -> set[str]:
    return {reason["code"] for reason in result.evaluation.reasons}


def _check_codes(result) -> set[str]:
    return {check["code"] for check in result.evaluation.checks}


def test_reserve_for_send_creates_transactional_reservation_without_adapter_or_outreach(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    result = ReserveForSendGateService(db_session).reserve("intent-1")
    db_session.commit()

    assert result.reservation is not None
    assert result.reservation.reservation_id == "reservation-intent-1"
    assert result.reservation.status == "reserved"
    assert result.reservation.normalized_recipient_email == "alex.hiring@example.com"
    assert result.evaluation.gate_result.status == "reserved_for_send"
    assert result.evaluation.gate_result.external_reservation_id == result.reservation.reservation_id
    assert result.evaluation.reasons == []
    assert "reservation_created" in _check_codes(result)
    AGENT_OUTPUT_MODELS["gate_result.schema.json"].model_validate(json.loads(result.evaluation.gate_result.raw_json))

    assert db_session.exec(select(OutreachRecord)).all() == []
    audit_actions = [audit.action for audit in db_session.exec(select(AuditLog)).all()]
    assert "send_reservation_created" in audit_actions
    assert "email_adapter_handoff_started" not in audit_actions
    assert "email_adapter_fake_completed" not in audit_actions


def test_reserve_for_send_is_idempotent_for_same_intent(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    first = ReserveForSendGateService(db_session).reserve("intent-1")
    second = ReserveForSendGateService(db_session).reserve("intent-1")
    db_session.commit()

    assert first.reservation is not None
    assert second.reservation is not None
    assert first.reservation.reservation_id == second.reservation.reservation_id
    reservations = db_session.exec(select(SendReservation)).all()
    assert len(reservations) == 1
    audit_actions = [audit.action for audit in db_session.exec(select(AuditLog)).all()]
    assert "send_reservation_reused" in audit_actions


def test_reserve_for_send_reuses_known_unsent_reservation_for_retry(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    first = ReserveForSendGateService(db_session).reserve("intent-1")
    assert first.reservation is not None
    first.reservation.status = "failed_known_unsent"
    db_session.add(first.reservation)
    db_session.commit()

    second = ReserveForSendGateService(db_session).reserve("intent-1")
    db_session.commit()

    assert second.reservation is not None
    assert second.reservation.reservation_id == first.reservation.reservation_id
    assert second.reservation.status == "reserved"
    assert second.evaluation.gate_result.status == "reserved_for_send"
    reservations = db_session.exec(select(SendReservation)).all()
    assert len(reservations) == 1
    audit_actions = [audit.action for audit in db_session.exec(select(AuditLog)).all()]
    assert "send_reservation_reused" in audit_actions


def test_reserve_for_send_does_not_reuse_stale_reservation_with_company_mismatch(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    first = ReserveForSendGateService(db_session).reserve("intent-1")
    assert first.reservation is not None
    first.reservation.company_policy_key = "domain:stale.example"
    db_session.add(first.reservation)
    db_session.commit()

    second = ReserveForSendGateService(db_session).reserve("intent-1")
    db_session.commit()

    assert second.reservation is None
    assert second.evaluation.gate_result.status == "blocked"
    assert "reservation_duplicate_recipient" in _reason_codes(second)
    reservation = db_session.exec(select(SendReservation).where(SendReservation.reservation_id == "reservation-intent-1")).one()
    assert reservation.company_policy_key == "domain:stale.example"


def test_reserve_for_send_does_not_reuse_stale_reservation_with_dedupe_mismatch(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    first = ReserveForSendGateService(db_session).reserve("intent-1")
    assert first.reservation is not None
    first.reservation.dedupe_recipient = False
    db_session.add(first.reservation)
    db_session.commit()

    second = ReserveForSendGateService(db_session).reserve("intent-1")
    db_session.commit()

    assert second.reservation is None
    assert second.evaluation.gate_result.status == "blocked"
    assert "reservation_duplicate_company" in _reason_codes(second)
    reservation = db_session.exec(select(SendReservation).where(SendReservation.reservation_id == "reservation-intent-1")).one()
    assert reservation.dedupe_recipient is False


def test_reserve_for_send_blocks_when_evaluate_only_blocks(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    intent = _intent(db_session)
    intent.source_refs_json = "[]"
    db_session.add(intent)
    db_session.commit()

    result = ReserveForSendGateService(db_session).reserve("intent-1")
    db_session.commit()

    assert result.reservation is None
    assert result.evaluation.gate_result.status == "blocked"
    assert "source_refs_missing" in _reason_codes(result)
    assert db_session.exec(select(SendReservation)).all() == []
    audit = db_session.exec(select(AuditLog).where(AuditLog.action == "send_reservation_skipped")).one()
    assert json.loads(audit.reason_codes_json) == ["evaluate_only_not_passed"]


def test_reserve_for_send_blocks_existing_active_recipient_reservation(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    intent = _intent(db_session)
    company = _company(db_session)
    db_session.add(
        SendReservation(
            reservation_id="reservation-existing-recipient",
            send_intent_id=None,
            normalized_recipient_email=intent.normalized_recipient_email,
            company_id=company.id,
            company_policy_key="domain:other.example",
            policy_snapshot_id=intent.policy_snapshot_id,
            status="active",
            dedupe_recipient=True,
            dedupe_company=False,
        )
    )
    db_session.commit()

    result = ReserveForSendGateService(db_session).reserve("intent-1")
    db_session.commit()

    assert result.reservation is None
    assert result.evaluation.gate_result.status == "blocked"
    assert "reservation_duplicate_recipient" in _reason_codes(result)
    assert len(db_session.exec(select(SendReservation)).all()) == 1


def test_reserve_for_send_blocks_existing_active_company_reservation(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    intent = _intent(db_session)
    company = _company(db_session)
    db_session.add(
        SendReservation(
            reservation_id="reservation-existing-company",
            send_intent_id=None,
            normalized_recipient_email="other@example.com",
            company_id=company.id,
            company_policy_key=company.company_policy_key,
            policy_snapshot_id=intent.policy_snapshot_id,
            status="reserved",
            dedupe_recipient=False,
            dedupe_company=True,
        )
    )
    db_session.commit()

    result = ReserveForSendGateService(db_session).reserve("intent-1")
    db_session.commit()

    assert result.reservation is None
    assert result.evaluation.gate_result.status == "blocked"
    assert "reservation_duplicate_company" in _reason_codes(result)
    assert len(db_session.exec(select(SendReservation)).all()) == 1


def test_reserve_for_send_reserved_gate_result_can_drive_private_fake_handoff(db_session, runs_root):
    from backend.app.email_delivery import EmailHandoffService, FakeDryRunEmailAdapter

    _import_valid_run(db_session, runs_root)
    result = ReserveForSendGateService(db_session).reserve("intent-1")
    assert result.reservation is not None
    adapter = FakeDryRunEmailAdapter()

    delivery = EmailHandoffService(db_session, adapter=adapter).handoff_reserved(result.evaluation.gate_result.gate_result_id)
    db_session.commit()

    assert delivery.status == "dry_run_recorded"
    assert delivery.network_performed is False
    assert len(adapter.messages) == 1
    assert db_session.exec(select(OutreachRecord)).all() == []
    gate_result = db_session.exec(select(ImportedGateResult).where(ImportedGateResult.gate_result_id == "gate-evaluate-only-intent-1")).one()
    assert gate_result.status == "reserved_for_send"
