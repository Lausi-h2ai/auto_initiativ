from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from backend.app.db.models import (
    AuditLog,
    Company,
    Contact,
    EmailDraft,
    ImportedFile,
    MasterCvProfileSnapshot,
    PolicySnapshot,
    Run,
    SendIntent,
    UserProfileSnapshot,
    utc_now,
)
from backend.app.db.normalization import normalize_recipient_email
from backend.app.gates.evaluate_only import EvaluateOnlyGateService, GateEvaluation


@dataclass(frozen=True)
class DraftQueueResult:
    send_intent: SendIntent
    gate_evaluation: GateEvaluation
    created: bool


class DraftQueueError(RuntimeError):
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


class DraftSendIntentQueueService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def queue_draft(self, draft_id: str, *, reviewer_id: str) -> DraftQueueResult:
        draft = self.session.exec(select(EmailDraft).where(EmailDraft.draft_id == draft_id)).first()
        if draft is None:
            raise DraftQueueError("draft_not_found", "Email draft not found.")

        existing = self.session.exec(select(SendIntent).where(SendIntent.external_email_draft_id == draft.draft_id)).first()
        if existing is not None:
            self._refresh_existing_intent(existing, draft)
            evaluation = EvaluateOnlyGateService(self.session).evaluate(existing.intent_id)
            self._audit(
                run_id=existing.run_id,
                action="send_intent_queue_reused",
                entity_id=existing.intent_id,
                result_status=evaluation.gate_result.status,
                metadata={"draft_id": draft.draft_id, "reviewer_id": reviewer_id},
            )
            return DraftQueueResult(send_intent=existing, gate_evaluation=evaluation, created=False)

        company = self.session.get(Company, draft.company_id) if draft.company_id is not None else None
        contact = self.session.get(Contact, draft.contact_id) if draft.contact_id is not None else None
        if company is None:
            raise DraftQueueError("draft_company_missing", "Draft is not linked to a company.")
        if contact is None:
            raise DraftQueueError("draft_contact_missing", "Draft is not linked to a contact.")

        user_profile = self._latest_approved(UserProfileSnapshot)
        master_cv = self._latest_approved(MasterCvProfileSnapshot)
        policy = self._latest_approved(PolicySnapshot)
        if user_profile is None or master_cv is None or policy is None:
            raise DraftQueueError(
                "approved_snapshots_missing",
                "Queueing requires approved user profile, master CV profile, and policy snapshots.",
            )

        run_id = self._run_id(draft)
        payload = self._payload(
            draft=draft,
            run_id=run_id,
            company=company,
            contact=contact,
            user_profile=user_profile,
            master_cv=master_cv,
            policy=policy,
        )
        intent = SendIntent(
            intent_id=payload["intent_id"],
            run_id=run_id,
            company_id=company.id,
            external_company_id=draft.external_company_id,
            contact_id=contact.id,
            external_contact_id=draft.external_contact_id,
            email_draft_id=draft.id,
            external_email_draft_id=draft.draft_id,
            raw_recipient_email=payload["recipient_email"],
            normalized_recipient_email=normalize_recipient_email(payload["recipient_email"]),
            recipient_name=payload.get("recipient_name"),
            company_domain=payload.get("company_domain"),
            subject=draft.subject,
            body_text=draft.body_text,
            body_html=draft.body_html,
            attachments_json=_json_dumps(payload["attachments"]),
            source_refs_json=draft.source_refs_json,
            claim_refs_json=draft.claim_refs_json,
            policy_snapshot_id=policy.id,
            external_policy_id=policy.policy_id,
            user_profile_snapshot_id=user_profile.id,
            external_profile_id=user_profile.profile_id,
            master_cv_profile_snapshot_id=master_cv.id,
            external_master_cv_profile_id=master_cv.profile_id,
            confidence=draft.confidence,
            review_flags_json=draft.review_flags_json,
            created_by="codex_agent",
            status="queued_for_send",
            raw_json=_json_dumps(payload),
            imported_file_id=draft.imported_file_id,
        )
        self.session.add(intent)
        self.session.flush()

        evaluation = EvaluateOnlyGateService(self.session).evaluate(intent.intent_id)
        self._audit(
            run_id=run_id,
            action="send_intent_queued_from_draft",
            entity_id=intent.intent_id,
            result_status=evaluation.gate_result.status,
            metadata={"draft_id": draft.draft_id, "reviewer_id": reviewer_id},
        )
        self.session.flush()
        return DraftQueueResult(send_intent=intent, gate_evaluation=evaluation, created=True)

    def _latest_approved(self, model: type[Any]) -> Any | None:
        return self.session.exec(select(model).where(model.status == "approved").order_by(model.imported_at.desc())).first()

    def _run_id(self, draft: EmailDraft) -> str:
        imported_file = self.session.get(ImportedFile, draft.imported_file_id) if draft.imported_file_id is not None else None
        if imported_file is not None:
            return imported_file.run_id
        return f"queued-{draft.draft_id}"

    def _payload(
        self,
        *,
        draft: EmailDraft,
        run_id: str,
        company: Company,
        contact: Contact,
        user_profile: UserProfileSnapshot,
        master_cv: MasterCvProfileSnapshot,
        policy: PolicySnapshot,
    ) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "intent_id": f"intent-{draft.draft_id}",
            "run_id": run_id,
            "company_id": draft.external_company_id,
            "contact_id": draft.external_contact_id,
            "email_draft_id": draft.draft_id,
            "recipient_email": contact.raw_email,
            "company_domain": company.normalized_domain,
            "subject": draft.subject,
            "body_text": draft.body_text,
            "attachments": self._attachments_with_existence(draft),
            "source_refs": _json_loads(draft.source_refs_json, []),
            "claim_refs": _json_loads(draft.claim_refs_json, []),
            "policy_id": policy.policy_id,
            "profile_id": user_profile.profile_id,
            "master_cv_profile_id": master_cv.profile_id,
            "confidence": draft.confidence,
            "review_flags": _json_loads(draft.review_flags_json, []),
            "created_by": "codex_agent",
        } | ({"recipient_name": contact.name} if contact.name is not None else {}) | (
            {"body_html": draft.body_html} if draft.body_html is not None else {}
        )

    def _refresh_existing_intent(self, intent: SendIntent, draft: EmailDraft) -> None:
        company = self.session.get(Company, draft.company_id) if draft.company_id is not None else None
        contact = self.session.get(Contact, draft.contact_id) if draft.contact_id is not None else None
        user_profile = self._latest_approved(UserProfileSnapshot)
        master_cv = self._latest_approved(MasterCvProfileSnapshot)
        policy = self._latest_approved(PolicySnapshot)
        if company is None or contact is None or user_profile is None or master_cv is None or policy is None:
            return
        payload = self._payload(
            draft=draft,
            run_id=intent.run_id,
            company=company,
            contact=contact,
            user_profile=user_profile,
            master_cv=master_cv,
            policy=policy,
        )
        intent.company_id = company.id
        intent.contact_id = contact.id
        intent.raw_recipient_email = payload["recipient_email"]
        intent.normalized_recipient_email = normalize_recipient_email(payload["recipient_email"])
        intent.recipient_name = payload.get("recipient_name")
        intent.company_domain = payload.get("company_domain")
        intent.subject = draft.subject
        intent.body_text = draft.body_text
        intent.raw_json = _json_dumps(payload)
        intent.attachments_json = _json_dumps(payload["attachments"])
        intent.source_refs_json = draft.source_refs_json
        intent.claim_refs_json = draft.claim_refs_json
        intent.policy_snapshot_id = policy.id
        intent.external_policy_id = policy.policy_id
        intent.user_profile_snapshot_id = user_profile.id
        intent.external_profile_id = user_profile.profile_id
        intent.master_cv_profile_snapshot_id = master_cv.id
        intent.external_master_cv_profile_id = master_cv.profile_id
        intent.body_html = draft.body_html
        intent.confidence = draft.confidence
        intent.review_flags_json = draft.review_flags_json
        intent.status = "queued_for_send"
        intent.updated_at = utc_now()
        self.session.add(intent)
        self.session.flush()

    def _attachments_with_existence(self, draft: EmailDraft) -> list[dict[str, Any]]:
        attachments = _json_loads(draft.attachments_json, [])
        if not isinstance(attachments, list):
            return []
        output_root = self._output_root(draft)
        normalized: list[dict[str, Any]] = []
        for attachment in attachments:
            if not isinstance(attachment, dict):
                continue
            copy = dict(attachment)
            copy["exists_at_draft_time"] = self._attachment_exists(output_root, copy.get("path"))
            normalized.append(copy)
        return normalized

    def _output_root(self, draft: EmailDraft) -> Path | None:
        imported_file = self.session.get(ImportedFile, draft.imported_file_id) if draft.imported_file_id is not None else None
        if imported_file is None:
            return None
        run = self.session.exec(select(Run).where(Run.run_id == imported_file.run_id)).first()
        if run is None:
            return Path(imported_file.path).resolve().parent
        return Path(run.output_path).resolve()

    def _attachment_exists(self, output_root: Path | None, path_value: Any) -> bool:
        if output_root is None or not isinstance(path_value, str) or not path_value:
            return False
        relative_path = Path(path_value.replace("\\", "/"))
        if relative_path.is_absolute():
            return False
        if relative_path.parts and relative_path.parts[0] == "output":
            relative_path = Path(*relative_path.parts[1:])
        return (output_root / relative_path).resolve().is_file()

    def _audit(
        self,
        *,
        run_id: str,
        action: str,
        entity_id: str,
        result_status: str,
        metadata: dict[str, Any],
    ) -> None:
        self.session.add(
            AuditLog(
                run_id=run_id,
                actor_type="backend",
                action=action,
                entity_type="send_intent",
                entity_id=entity_id,
                result_status=result_status,
                reason_codes_json="[]",
                metadata_json=_json_dumps(metadata),
                created_at=utc_now(),
            )
        )
