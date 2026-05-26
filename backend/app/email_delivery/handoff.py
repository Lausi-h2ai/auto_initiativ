from __future__ import annotations

import json
from typing import Any

from sqlmodel import Session, select

from backend.app.db.models import AuditLog, Company, ImportedGateResult, SendIntent, SendReservation
from backend.app.email_delivery.adapters import EmailAdapter, EmailDeliveryResult, EmailMessage, FakeDryRunEmailAdapter


RESERVATION_STATUSES_READY_FOR_HANDOFF = {"active", "reserved"}
ALLOWED_PHASE_7_ADAPTER_PROVIDER = "fake_dry_run"


class EmailHandoffPreconditionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


class EmailHandoffService:
    def __init__(self, session: Session, adapter: EmailAdapter | None = None) -> None:
        self.session = session
        self.adapter = adapter or FakeDryRunEmailAdapter()

    def handoff_reserved(self, gate_result_id: str) -> EmailDeliveryResult:
        if type(self.adapter) is not FakeDryRunEmailAdapter or self.adapter.provider != ALLOWED_PHASE_7_ADAPTER_PROVIDER:
            raise EmailHandoffPreconditionError(
                "fake_adapter_required",
                "Only the fake dry-run adapter is allowed in this phase.",
            )

        gate_result = self.session.exec(
            select(ImportedGateResult).where(ImportedGateResult.gate_result_id == gate_result_id)
        ).first()
        if gate_result is None:
            raise EmailHandoffPreconditionError("gate_result_missing", "Gate result could not be resolved.")

        intent = self._resolve_intent(gate_result)
        reservation = self._validate_gate_and_reservation(gate_result, intent)
        self._audit(
            intent=intent,
            action="email_adapter_handoff_started",
            result_status="started",
            metadata={
                "adapter_provider": self.adapter.provider,
                "gate_result_id": gate_result.gate_result_id,
                "reservation_id": reservation.reservation_id,
            },
        )
        self.session.flush()

        try:
            result = self.adapter.send(self._message_from_intent(intent))
        except Exception as exc:
            self._audit(
                intent=intent,
                action="email_adapter_fake_failed",
                result_status="failed",
                metadata={
                    "adapter_provider": self.adapter.provider,
                    "error_type": type(exc).__name__,
                    "gate_result_id": gate_result.gate_result_id,
                    "reservation_id": reservation.reservation_id,
                },
            )
            self.session.flush()
            raise

        self._audit(
            intent=intent,
            action="email_adapter_fake_completed",
            result_status=result.status,
            metadata={
                "adapter_provider": result.provider,
                "gate_result_id": gate_result.gate_result_id,
                "network_performed": result.network_performed,
                "provider_message_id": result.provider_message_id,
                "reservation_id": reservation.reservation_id,
            },
        )
        self.session.flush()
        return result

    def _resolve_intent(self, gate_result: ImportedGateResult) -> SendIntent:
        intent = self.session.get(SendIntent, gate_result.send_intent_id) if gate_result.send_intent_id is not None else None
        if intent is None:
            intent = self.session.exec(select(SendIntent).where(SendIntent.intent_id == gate_result.external_intent_id)).first()
        if intent is None:
            raise EmailHandoffPreconditionError("send_intent_missing", "Send intent could not be resolved.")
        return intent

    def _validate_gate_and_reservation(self, gate_result: ImportedGateResult, intent: SendIntent) -> SendReservation:
        if gate_result.status != "reserved_for_send":
            raise EmailHandoffPreconditionError(
                "reserved_gate_required",
                "Adapter handoff requires a reserved_for_send gate result.",
            )

        reasons = _json_loads(gate_result.reasons_json, [])
        if reasons:
            raise EmailHandoffPreconditionError("gate_reasons_present", "Reserved gate result must not contain reasons.")

        if not gate_result.external_reservation_id:
            raise EmailHandoffPreconditionError("reservation_required", "Gate result has no reservation id.")

        reservation = self.session.exec(
            select(SendReservation).where(SendReservation.reservation_id == gate_result.external_reservation_id)
        ).first()
        if reservation is None:
            raise EmailHandoffPreconditionError("reservation_missing", "Reservation could not be resolved.")
        if reservation.status not in RESERVATION_STATUSES_READY_FOR_HANDOFF:
            raise EmailHandoffPreconditionError("reservation_not_active", "Reservation is not active for adapter handoff.")
        if reservation.send_intent_id != intent.id:
            raise EmailHandoffPreconditionError("reservation_intent_mismatch", "Reservation does not match send intent.")
        if reservation.normalized_recipient_email != intent.normalized_recipient_email:
            raise EmailHandoffPreconditionError("reservation_recipient_mismatch", "Reservation does not match recipient.")
        if reservation.policy_snapshot_id != intent.policy_snapshot_id:
            raise EmailHandoffPreconditionError("reservation_policy_mismatch", "Reservation does not match policy snapshot.")

        company = self.session.get(Company, intent.company_id) if intent.company_id is not None else None
        if company is None:
            raise EmailHandoffPreconditionError("company_missing", "Company could not be resolved for reservation check.")
        if reservation.company_id != company.id or reservation.company_policy_key != company.company_policy_key:
            raise EmailHandoffPreconditionError("reservation_company_mismatch", "Reservation does not match company.")

        return reservation

    def _message_from_intent(self, intent: SendIntent) -> EmailMessage:
        attachments = _json_loads(intent.attachments_json, [])
        return EmailMessage(
            intent_id=intent.intent_id,
            recipient_email=intent.raw_recipient_email,
            subject=intent.subject,
            body_text=intent.body_text,
            body_html=intent.body_html,
            attachments=attachments if isinstance(attachments, list) else [],
        )

    def _audit(self, *, intent: SendIntent, action: str, result_status: str, metadata: dict[str, Any]) -> None:
        self.session.add(
            AuditLog(
                run_id=intent.run_id,
                actor_type="backend",
                action=action,
                entity_type="email_adapter_handoff",
                entity_id=intent.intent_id,
                result_status=result_status,
                reason_codes_json="[]",
                metadata_json=_json_dumps(metadata),
            )
        )
