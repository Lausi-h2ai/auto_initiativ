from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from backend.app.core.config import Settings, get_settings
from backend.app.db.models import (
    AuditLog,
    Company,
    Contact,
    EmailDraft,
    ImportedFile,
    OutreachRecord,
    SendApprovalSnapshot,
    SendIntent,
    SendReservation,
    SentMessage,
    utc_now,
)
from backend.app.email_delivery.adapters import EmailAdapter, EmailDeliveryResult, EmailMessage, GmailEmailAdapter
from backend.app.gates.reserve_for_send import ReserveForSendGateService


BLOCKING_OUTREACH_STATUSES = {"sent", "provider_accepted", "outcome_uncertain"}
NON_BLOCKING_OUTREACH_STATUSES = {"provider_rejected_known_unsent", "failed_precondition", "cancelled", "released", "void"}
SEND_BATCH_TERMINAL_STATUSES = {
    "sent",
    "blocked",
    "needs_review",
    "reservation_failed",
    "send_disabled",
    "send_failed_known_unsent",
    "send_failed_uncertain",
}


class KnownUnsentEmailError(RuntimeError):
    """Raised when no provider send occurred or provider explicitly rejected before accepting."""


@dataclass(frozen=True)
class SendBatchItemResult:
    intent_id: str
    status: str
    approval_id: str | None = None
    gate_result_id: str | None = None
    reservation_id: str | None = None
    sent_message_id: str | None = None
    outreach_record_id: str | None = None
    reason_codes: list[str] = field(default_factory=list)
    detail: str | None = None


@dataclass(frozen=True)
class SendBatchResult:
    batch_id: str
    status: str
    requested_count: int
    sent_count: int
    blocked_count: int
    items: list[SendBatchItemResult]


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None, fallback: Any) -> Any:
    if value is None:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_json(value: Any) -> str:
    return _sha256_bytes(_json_dumps(value).encode("utf-8"))


def _file_hash(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SendBatchService:
    def __init__(
        self,
        session: Session,
        *,
        settings: Settings | None = None,
        adapter: EmailAdapter | None = None,
        sending_enabled: bool | None = None,
    ) -> None:
        self.session = session
        self.settings = settings or get_settings()
        self.adapter = adapter
        self.sending_enabled = self.settings.email_sending_enabled if sending_enabled is None else sending_enabled

    def approve_and_send(self, intent_ids: list[str], reviewer_id: str) -> SendBatchResult:
        batch_id = f"send-batch-{uuid4().hex}"
        items = [self._process_item(batch_id=batch_id, intent_id=intent_id, reviewer_id=reviewer_id) for intent_id in intent_ids]
        sent_count = sum(1 for item in items if item.status == "sent")
        blocked_count = sum(1 for item in items if item.status != "sent")
        status = "completed" if blocked_count == 0 else "completed_with_blocks" if sent_count else "blocked"
        return SendBatchResult(
            batch_id=batch_id,
            status=status,
            requested_count=len(intent_ids),
            sent_count=sent_count,
            blocked_count=blocked_count,
            items=items,
        )

    def _process_item(self, *, batch_id: str, intent_id: str, reviewer_id: str) -> SendBatchItemResult:
        intent = self.session.exec(select(SendIntent).where(SendIntent.intent_id == intent_id)).first()
        if intent is None:
            return SendBatchItemResult(intent_id=intent_id, status="blocked", reason_codes=["send_intent_missing"])

        approval = self._approval_snapshot(batch_id=batch_id, intent=intent, reviewer_id=reviewer_id)
        self._audit(
            intent=intent,
            action="send_approval_snapshot_created",
            result_status="approved",
            metadata={"approval_id": approval.approval_id, "batch_id": batch_id, "payload_hash": approval.payload_hash},
        )

        if not self.sending_enabled and self.adapter is None:
            self._set_intent_status(intent, "send_disabled")
            self._audit(
                intent=intent,
                action="email_send_skipped",
                result_status="send_disabled",
                reason_codes=["email_sending_disabled"],
                metadata={"approval_id": approval.approval_id, "batch_id": batch_id},
            )
            return SendBatchItemResult(
                intent_id=intent_id,
                status="send_disabled",
                approval_id=approval.approval_id,
                reason_codes=["email_sending_disabled"],
            )

        hash_mismatch = self._verify_approval_hashes(approval)
        if hash_mismatch:
            self._set_intent_status(intent, "blocked")
            self._audit(
                intent=intent,
                action="email_send_skipped",
                result_status="blocked",
                reason_codes=["approval_payload_changed"],
                metadata={"approval_id": approval.approval_id, "changed_attachments": hash_mismatch},
            )
            return SendBatchItemResult(
                intent_id=intent_id,
                status="blocked",
                approval_id=approval.approval_id,
                reason_codes=["approval_payload_changed"],
                detail="Approved attachment payload changed after approval.",
            )

        reservation_result = ReserveForSendGateService(self.session).reserve(intent_id)
        gate = reservation_result.evaluation.gate_result
        if reservation_result.reservation is None:
            self._set_intent_status(intent, "reservation_failed" if gate.status == "passed_evaluate_only" else gate.status)
            return SendBatchItemResult(
                intent_id=intent_id,
                status="reservation_failed" if gate.status == "passed_evaluate_only" else gate.status,
                approval_id=approval.approval_id,
                gate_result_id=gate.gate_result_id,
                reason_codes=[reason["code"] for reason in reservation_result.evaluation.reasons],
            )

        reservation = reservation_result.reservation
        reservation.status = "attempting_provider_send"
        self.session.add(reservation)
        self._audit(
            intent=intent,
            action="email_provider_send_started",
            result_status="attempting_provider_send",
            metadata={"approval_id": approval.approval_id, "reservation_id": reservation.reservation_id},
        )
        self.session.flush()

        try:
            delivery = self._adapter().send(self._message_from_approval(approval))
        except KnownUnsentEmailError as exc:
            self._set_intent_status(intent, "send_failed_known_unsent")
            reservation.status = "failed_known_unsent"
            self.session.add(reservation)
            sent_message = self._sent_message(
                approval=approval,
                intent=intent,
                reservation=reservation,
                status="provider_rejected_known_unsent",
                delivery=None,
                error=exc,
            )
            self._audit(
                intent=intent,
                action="email_provider_send_failed_known_unsent",
                result_status="provider_rejected_known_unsent",
                reason_codes=["provider_rejected_known_unsent"],
                metadata={"approval_id": approval.approval_id, "reservation_id": reservation.reservation_id},
            )
            return SendBatchItemResult(
                intent_id=intent_id,
                status="send_failed_known_unsent",
                approval_id=approval.approval_id,
                gate_result_id=gate.gate_result_id,
                reservation_id=reservation.reservation_id,
                sent_message_id=sent_message.sent_message_id,
                reason_codes=["provider_rejected_known_unsent"],
                detail=str(exc),
            )
        except Exception as exc:
            self._set_intent_status(intent, "send_failed_uncertain")
            reservation.status = "outcome_uncertain"
            self.session.add(reservation)
            sent_message = self._sent_message(
                approval=approval,
                intent=intent,
                reservation=reservation,
                status="send_failed_uncertain",
                delivery=None,
                error=exc,
            )
            outreach = self._blocking_outreach(
                approval=approval,
                intent=intent,
                reservation=reservation,
                status="outcome_uncertain",
                sent_message=sent_message,
            )
            self._audit(
                intent=intent,
                action="email_provider_send_uncertain",
                result_status="outcome_uncertain",
                reason_codes=["provider_outcome_uncertain"],
                metadata={
                    "approval_id": approval.approval_id,
                    "reservation_id": reservation.reservation_id,
                    "outreach_record_id": outreach.outreach_record_id,
                    "error_type": type(exc).__name__,
                },
            )
            return SendBatchItemResult(
                intent_id=intent_id,
                status="send_failed_uncertain",
                approval_id=approval.approval_id,
                gate_result_id=gate.gate_result_id,
                reservation_id=reservation.reservation_id,
                sent_message_id=sent_message.sent_message_id,
                outreach_record_id=outreach.outreach_record_id,
                reason_codes=["provider_outcome_uncertain"],
                detail=str(exc),
            )

        self._set_intent_status(intent, "sent")
        reservation.status = "released"
        reservation.released_at = utc_now()
        self.session.add(reservation)
        sent_message = self._sent_message(
            approval=approval,
            intent=intent,
            reservation=reservation,
            status="provider_accepted",
            delivery=delivery,
            error=None,
        )
        outreach = self._blocking_outreach(
            approval=approval,
            intent=intent,
            reservation=reservation,
            status="sent",
            sent_message=sent_message,
        )
        self._audit(
            intent=intent,
            action="email_provider_send_completed",
            result_status="sent",
            metadata={
                "approval_id": approval.approval_id,
                "reservation_id": reservation.reservation_id,
                "sent_message_id": sent_message.sent_message_id,
                "outreach_record_id": outreach.outreach_record_id,
                "provider": delivery.provider,
                "provider_message_id": delivery.provider_message_id,
            },
        )
        return SendBatchItemResult(
            intent_id=intent_id,
            status="sent",
            approval_id=approval.approval_id,
            gate_result_id=gate.gate_result_id,
            reservation_id=reservation.reservation_id,
            sent_message_id=sent_message.sent_message_id,
            outreach_record_id=outreach.outreach_record_id,
        )

    def _approval_snapshot(self, *, batch_id: str, intent: SendIntent, reviewer_id: str) -> SendApprovalSnapshot:
        existing = self.session.exec(
            select(SendApprovalSnapshot).where(
                SendApprovalSnapshot.batch_id == batch_id,
                SendApprovalSnapshot.external_intent_id == intent.intent_id,
            )
        ).first()
        if existing is not None:
            return existing

        company = self.session.get(Company, intent.company_id) if intent.company_id is not None else None
        attachments = self._freeze_attachments(intent)
        frozen = {
            "intent_id": intent.intent_id,
            "recipient_email": intent.raw_recipient_email,
            "normalized_recipient_email": intent.normalized_recipient_email,
            "subject": intent.subject,
            "body_text": intent.body_text,
            "body_html": intent.body_html,
            "attachments": attachments,
            "company_policy_key": company.company_policy_key if company is not None else "",
            "company_identity_key": company.company_policy_key if company is not None else "",
            "policy_snapshot_id": intent.policy_snapshot_id,
            "user_profile_snapshot_id": intent.user_profile_snapshot_id,
            "master_cv_profile_snapshot_id": intent.master_cv_profile_snapshot_id,
            "email_draft_id": intent.email_draft_id,
            "source_refs": _json_loads(intent.source_refs_json, []),
            "claim_refs": _json_loads(intent.claim_refs_json, []),
        }
        approval = SendApprovalSnapshot(
            approval_id=f"approval-{uuid4().hex}",
            batch_id=batch_id,
            send_intent_id=intent.id,
            external_intent_id=intent.intent_id,
            reviewer_id=reviewer_id,
            normalized_recipient_email=intent.normalized_recipient_email,
            raw_recipient_email=intent.raw_recipient_email,
            subject=intent.subject,
            body_text=intent.body_text,
            body_html=intent.body_html,
            company_id=company.id if company is not None else None,
            company_policy_key=company.company_policy_key if company is not None else "",
            company_identity_key=company.company_policy_key if company is not None else "",
            policy_snapshot_id=intent.policy_snapshot_id,
            user_profile_snapshot_id=intent.user_profile_snapshot_id,
            master_cv_profile_snapshot_id=intent.master_cv_profile_snapshot_id,
            email_draft_id=intent.email_draft_id,
            payload_hash=_hash_json(frozen),
            attachments_json=_json_dumps(attachments),
            source_refs_json=intent.source_refs_json,
            claim_refs_json=intent.claim_refs_json,
            frozen_json=_json_dumps(frozen),
        )
        self.session.add(approval)
        self.session.flush()
        return approval

    def _freeze_attachments(self, intent: SendIntent) -> list[dict[str, Any]]:
        attachments = _json_loads(intent.attachments_json, [])
        if not isinstance(attachments, list):
            return []
        output_root = self._output_root(intent)
        frozen: list[dict[str, Any]] = []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            copy = dict(attachment)
            path_value = copy.get("path")
            resolved_path = self._resolve_attachment_path(output_root, path_value) if isinstance(path_value, str) else None
            copy["resolved_path"] = str(resolved_path) if resolved_path is not None else None
            copy["sha256"] = _file_hash(resolved_path) if resolved_path is not None else None
            frozen.append(copy)
        return frozen

    def _output_root(self, intent: SendIntent) -> Path | None:
        if intent.imported_file_id is None:
            return None
        imported_file = self.session.get(ImportedFile, intent.imported_file_id)
        if imported_file is None:
            return None
        return Path(imported_file.path).resolve().parent

    def _resolve_attachment_path(self, output_root: Path | None, path_value: str) -> Path | None:
        if output_root is None:
            return None
        relative_path = Path(path_value.replace("\\", "/"))
        if relative_path.is_absolute():
            return None
        if relative_path.parts and relative_path.parts[0] == "output":
            relative_path = Path(*relative_path.parts[1:])
        return (output_root / relative_path).resolve()

    def _verify_approval_hashes(self, approval: SendApprovalSnapshot) -> list[str]:
        changed: list[str] = []
        attachments = _json_loads(approval.attachments_json, [])
        if not isinstance(attachments, list):
            return ["attachments_json"]
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            expected = attachment.get("sha256")
            resolved_path = attachment.get("resolved_path")
            if not expected or not isinstance(resolved_path, str):
                continue
            actual = _file_hash(Path(resolved_path))
            if actual != expected:
                changed.append(str(attachment.get("attachment_id") or resolved_path))
        return changed

    def _message_from_approval(self, approval: SendApprovalSnapshot) -> EmailMessage:
        attachments = _json_loads(approval.attachments_json, [])
        recipient_email = approval.raw_recipient_email
        subject = approval.subject
        body_text = approval.body_text
        body_html = approval.body_html
        headers = {
            "X-Auto-Initiativ-Intent-ID": approval.external_intent_id,
            "X-Auto-Initiativ-Approval-ID": approval.approval_id,
        }
        if self.adapter is None and self.settings.email_provider == "gmail_sandbox":
            if not self.settings.gmail_sandbox_recipient:
                raise KnownUnsentEmailError("Gmail sandbox recipient is not configured.")
            recipient_email = self.settings.gmail_sandbox_recipient
            subject = f"[SANDBOX to {approval.raw_recipient_email}] {approval.subject}"
            body_text = (
                "SANDBOX DELIVERY\n"
                f"Original recipient: {approval.raw_recipient_email}\n"
                f"Intent ID: {approval.external_intent_id}\n\n"
                f"{approval.body_text}"
            )
            if body_html:
                body_html = (
                    "<p><strong>SANDBOX DELIVERY</strong><br>"
                    f"Original recipient: {approval.raw_recipient_email}<br>"
                    f"Intent ID: {approval.external_intent_id}</p>"
                    f"{body_html}"
                )
            headers["X-Auto-Initiativ-Original-Recipient"] = approval.raw_recipient_email
            headers["X-Auto-Initiativ-Sandbox-Recipient"] = recipient_email
        return EmailMessage(
            intent_id=approval.external_intent_id,
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            attachments=attachments if isinstance(attachments, list) else [],
            headers=headers,
        )

    def _adapter(self) -> EmailAdapter:
        if self.adapter is not None:
            return self.adapter
        if self.settings.email_provider == "gmail" and not self.settings.email_allow_real_recipients:
            raise KnownUnsentEmailError("Real-recipient Gmail sending requires EMAIL_ALLOW_REAL_RECIPIENTS=true.")
        if self.settings.email_provider not in {"gmail", "gmail_sandbox"}:
            raise KnownUnsentEmailError(f"Unsupported email provider: {self.settings.email_provider}")
        return GmailEmailAdapter(self.settings)

    def _sent_message(
        self,
        *,
        approval: SendApprovalSnapshot,
        intent: SendIntent,
        reservation: SendReservation,
        status: str,
        delivery: EmailDeliveryResult | None,
        error: Exception | None,
    ) -> SentMessage:
        sent_message = SentMessage(
            sent_message_id=f"sent-message-{uuid4().hex}",
            approval_snapshot_id=approval.id,
            send_intent_id=intent.id,
            reservation_id=reservation.id,
            provider=delivery.provider if delivery is not None else self._adapter_provider(),
            provider_message_id=delivery.provider_message_id if delivery is not None else None,
            provider_thread_id=delivery.provider_thread_id if delivery is not None else None,
            status=status,
            normalized_recipient_email=approval.normalized_recipient_email,
            company_policy_key=approval.company_policy_key,
            network_performed=delivery.network_performed if delivery is not None else False,
            provider_response_json=_json_dumps(delivery.metadata if delivery is not None else {}),
            error_json=_json_dumps({"error_type": type(error).__name__, "message": str(error)} if error is not None else {}),
            accepted_at=utc_now() if status == "provider_accepted" else None,
        )
        self.session.add(sent_message)
        self.session.flush()
        return sent_message

    def _adapter_provider(self) -> str:
        if self.adapter is not None:
            return self.adapter.provider
        return self.settings.email_provider

    def _set_intent_status(self, intent: SendIntent, status: str) -> None:
        intent.status = status
        intent.updated_at = utc_now()
        self.session.add(intent)

    def _blocking_outreach(
        self,
        *,
        approval: SendApprovalSnapshot,
        intent: SendIntent,
        reservation: SendReservation,
        status: str,
        sent_message: SentMessage,
    ) -> OutreachRecord:
        contact = self.session.get(Contact, intent.contact_id) if intent.contact_id is not None else None
        existing = self.session.exec(
            select(OutreachRecord).where(OutreachRecord.outreach_record_id == f"outreach-{approval.approval_id}")
        ).first()
        outreach = existing or OutreachRecord(
            outreach_record_id=f"outreach-{approval.approval_id}",
            send_intent_id=intent.id,
            company_id=approval.company_id,
            contact_id=contact.id if contact is not None else None,
            normalized_recipient_email=approval.normalized_recipient_email,
            company_policy_key=approval.company_policy_key,
            policy_snapshot_id=approval.policy_snapshot_id,
            channel="email",
            status=status,
            source="backend",
        )
        outreach.status = status
        outreach.dedupe_recipient = True
        outreach.dedupe_company = True
        outreach.occurred_at = utc_now()
        outreach.notes_json = _json_dumps(
            {
                "approval_id": approval.approval_id,
                "reservation_id": reservation.reservation_id,
                "sent_message_id": sent_message.sent_message_id,
                "blocking": status in BLOCKING_OUTREACH_STATUSES,
            }
        )
        self.session.add(outreach)
        self.session.flush()
        return outreach

    def _audit(
        self,
        *,
        intent: SendIntent,
        action: str,
        result_status: str,
        metadata: dict[str, Any],
        reason_codes: list[str] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                run_id=intent.run_id,
                actor_type="backend",
                action=action,
                entity_type="email_send",
                entity_id=intent.intent_id,
                result_status=result_status,
                reason_codes_json=_json_dumps(reason_codes or []),
                metadata_json=_json_dumps(metadata),
            )
        )
        self.session.flush()
