from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from backend.app.db.models import AuditLog, Company, ImportedGateResult, PolicySnapshot, SendIntent, SendReservation
from backend.app.gates.evaluate_only import GateEvaluation, EvaluateOnlyGateService


ACTIVE_RESERVATION_STATUSES = {"active", "reserved", "attempting_provider_send", "outcome_uncertain"}


@dataclass(frozen=True)
class ReservationGateResult:
    evaluation: GateEvaluation
    reservation: SendReservation | None


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _reason(code: str, message: str, *, field: str | None = None) -> dict[str, str]:
    reason = {"code": code, "message": message}
    if field is not None:
        reason["field"] = field
    return reason


class ReserveForSendGateService:
    def __init__(self, session: Session, evaluate_only_service: EvaluateOnlyGateService | None = None) -> None:
        self.session = session
        self.evaluate_only_service = evaluate_only_service or EvaluateOnlyGateService(session)

    def reserve(self, intent_id: str) -> ReservationGateResult:
        evaluation = self.evaluate_only_service.evaluate(intent_id)
        if evaluation.gate_result.status != "passed_evaluate_only":
            self._audit_reservation_skipped(evaluation.gate_result, "evaluate_only_not_passed")
            return ReservationGateResult(evaluation=evaluation, reservation=None)

        intent = self._intent(evaluation.gate_result)
        company = self.session.get(Company, intent.company_id) if intent.company_id is not None else None
        policy = self.session.get(PolicySnapshot, intent.policy_snapshot_id) if intent.policy_snapshot_id is not None else None
        if company is None or policy is None:
            self._block(evaluation, "reservation_required_record_missing", "Reservation required record is missing.")
            return ReservationGateResult(evaluation=evaluation, reservation=None)

        policy_payload = _json_loads(policy.raw_json, {})
        outreach_policy = policy_payload.get("outreach", {}) if isinstance(policy_payload, dict) else {}
        dedupe_recipient = not bool(outreach_policy.get("allow_recipient_repeat", False))
        dedupe_company = not bool(outreach_policy.get("allow_company_repeat", False))

        existing = self._matching_existing_reservation(
            intent,
            company,
            dedupe_recipient=dedupe_recipient,
            dedupe_company=dedupe_company,
        )
        if existing is not None:
            self._mark_reserved(evaluation, existing)
            self._audit_reservation_created(evaluation.gate_result, existing, reused=True)
            return ReservationGateResult(evaluation=evaluation, reservation=existing)

        conflict = self._reservation_conflict(intent, company, dedupe_recipient=dedupe_recipient, dedupe_company=dedupe_company)
        if conflict is not None:
            code, message, field = conflict
            self._block(evaluation, code, message, field=field)
            self._audit_reservation_skipped(evaluation.gate_result, code)
            return ReservationGateResult(evaluation=evaluation, reservation=None)

        reservation = SendReservation(
            reservation_id=self._reservation_id(intent.intent_id),
            send_intent_id=intent.id,
            normalized_recipient_email=intent.normalized_recipient_email,
            company_id=company.id,
            company_policy_key=company.company_policy_key,
            policy_snapshot_id=intent.policy_snapshot_id,
            status="reserved",
            dedupe_recipient=dedupe_recipient,
            dedupe_company=dedupe_company,
            notes_json=_json_dumps({"mode": "reserve_for_send", "gate_result_id": evaluation.gate_result.gate_result_id}),
        )
        try:
            with self.session.begin_nested():
                self.session.add(reservation)
                self.session.flush()
        except IntegrityError:
            self._block(
                evaluation,
                "reservation_unique_conflict",
                "Transactional reservation failed because an active reservation already exists.",
            )
            self._audit_reservation_skipped(evaluation.gate_result, "reservation_unique_conflict")
            return ReservationGateResult(evaluation=evaluation, reservation=None)

        self._mark_reserved(evaluation, reservation)
        self._audit_reservation_created(evaluation.gate_result, reservation, reused=False)
        self.session.flush()
        return ReservationGateResult(evaluation=evaluation, reservation=reservation)

    def _intent(self, gate_result: ImportedGateResult) -> SendIntent:
        intent = self.session.get(SendIntent, gate_result.send_intent_id) if gate_result.send_intent_id is not None else None
        if intent is None:
            intent = self.session.exec(select(SendIntent).where(SendIntent.intent_id == gate_result.external_intent_id)).first()
        if intent is None:
            raise ValueError(f"Send intent not found: {gate_result.external_intent_id}")
        return intent

    def _matching_existing_reservation(
        self,
        intent: SendIntent,
        company: Company,
        *,
        dedupe_recipient: bool,
        dedupe_company: bool,
    ) -> SendReservation | None:
        reservation = self.session.exec(
            select(SendReservation).where(SendReservation.reservation_id == self._reservation_id(intent.intent_id))
        ).first()
        if (
            reservation is not None
            and reservation.send_intent_id == intent.id
            and reservation.normalized_recipient_email == intent.normalized_recipient_email
            and reservation.company_id == company.id
            and reservation.company_policy_key == company.company_policy_key
            and reservation.policy_snapshot_id == intent.policy_snapshot_id
            and reservation.status in ACTIVE_RESERVATION_STATUSES
            and reservation.dedupe_recipient == dedupe_recipient
            and reservation.dedupe_company == dedupe_company
        ):
            return reservation
        return None

    def _reservation_conflict(
        self,
        intent: SendIntent,
        company: Company,
        *,
        dedupe_recipient: bool,
        dedupe_company: bool,
    ) -> tuple[str, str, str] | None:
        if dedupe_recipient:
            duplicate_recipient = self.session.exec(
                select(SendReservation).where(
                    SendReservation.normalized_recipient_email == intent.normalized_recipient_email,
                    SendReservation.status.in_(ACTIVE_RESERVATION_STATUSES),
                    SendReservation.dedupe_recipient == True,  # noqa: E712
                )
            ).first()
            if duplicate_recipient is not None:
                return ("reservation_duplicate_recipient", "Recipient already has an active reservation.", "recipient_email")

        if dedupe_company:
            duplicate_company = self.session.exec(
                select(SendReservation).where(
                    SendReservation.company_policy_key == company.company_policy_key,
                    SendReservation.status.in_(ACTIVE_RESERVATION_STATUSES),
                    SendReservation.dedupe_company == True,  # noqa: E712
                )
            ).first()
            if duplicate_company is not None:
                return ("reservation_duplicate_company", "Company already has an active reservation.", "company_id")
        return None

    def _mark_reserved(self, evaluation: GateEvaluation, reservation: SendReservation) -> None:
        checks = list(evaluation.checks)
        checks.append(
            {
                "code": "reservation_created",
                "status": "pass",
                "details": "Transactional send reservation is available.",
            }
        )
        raw_result = dict(evaluation.raw_result)
        raw_result["status"] = "reserved_for_send"
        raw_result["reservation_id"] = reservation.reservation_id
        raw_result["checks"] = checks
        raw_result["reasons"] = []

        gate_result = evaluation.gate_result
        gate_result.status = "reserved_for_send"
        gate_result.checks_json = _json_dumps(checks)
        gate_result.reasons_json = "[]"
        gate_result.external_reservation_id = reservation.reservation_id
        gate_result.raw_json = _json_dumps(raw_result)
        self.session.add(gate_result)
        evaluation.checks[:] = checks
        evaluation.reasons[:] = []
        evaluation.raw_result.clear()
        evaluation.raw_result.update(raw_result)

    def _block(self, evaluation: GateEvaluation, code: str, message: str, *, field: str | None = None) -> None:
        checks = list(evaluation.checks)
        reasons = list(evaluation.reasons)
        checks.append({"code": code, "status": "fail", "details": message})
        reasons.append(_reason(code, message, field=field))
        raw_result = dict(evaluation.raw_result)
        raw_result["status"] = "blocked"
        raw_result["checks"] = checks
        raw_result["reasons"] = reasons
        raw_result.pop("reservation_id", None)

        gate_result = evaluation.gate_result
        gate_result.status = "blocked"
        gate_result.checks_json = _json_dumps(checks)
        gate_result.reasons_json = _json_dumps(reasons)
        gate_result.external_reservation_id = None
        gate_result.raw_json = _json_dumps(raw_result)
        self.session.add(gate_result)
        evaluation.checks[:] = checks
        evaluation.reasons[:] = reasons
        evaluation.raw_result.clear()
        evaluation.raw_result.update(raw_result)

    def _audit_reservation_created(self, gate_result: ImportedGateResult, reservation: SendReservation, *, reused: bool) -> None:
        self.session.add(
            AuditLog(
                run_id=self._intent(gate_result).run_id,
                actor_type="backend",
                action="send_reservation_created" if not reused else "send_reservation_reused",
                entity_type="send_reservation",
                entity_id=reservation.reservation_id,
                result_status="reserved",
                reason_codes_json="[]",
                metadata_json=_json_dumps(
                    {
                        "gate_result_id": gate_result.gate_result_id,
                        "send_intent_id": gate_result.external_intent_id,
                        "mode": "reserve_for_send",
                    }
                ),
            )
        )

    def _audit_reservation_skipped(self, gate_result: ImportedGateResult, reason_code: str) -> None:
        self.session.add(
            AuditLog(
                run_id=self._intent(gate_result).run_id,
                actor_type="backend",
                action="send_reservation_skipped",
                entity_type="send_reservation",
                entity_id=None,
                result_status="blocked",
                reason_codes_json=_json_dumps([reason_code]),
                metadata_json=_json_dumps(
                    {
                        "gate_result_id": gate_result.gate_result_id,
                        "send_intent_id": gate_result.external_intent_id,
                        "mode": "reserve_for_send",
                    }
                ),
            )
        )

    def _reservation_id(self, intent_id: str) -> str:
        return f"reservation-{intent_id}"
