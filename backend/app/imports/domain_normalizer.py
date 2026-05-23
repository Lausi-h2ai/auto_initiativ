from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from hashlib import sha256
from typing import Any

from sqlmodel import Session, col, select

from backend.app.db.models import (
    AuditLog,
    Company,
    Contact,
    EmailDraft,
    FitEvaluation,
    ImportedFile,
    ImportedGateResult,
    MasterCvProfileSnapshot,
    PolicySnapshot,
    SendIntent,
    UserProfileSnapshot,
)
from backend.app.db.normalization import (
    build_company_policy_key,
    normalize_company_domain,
    normalize_company_name,
    normalize_recipient_email,
)
from backend.app.onboarding.promotion import SNAPSHOT_STATUS_CANDIDATE


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None) -> dict[str, Any]:
    if value is None:
        raise ValueError("Cannot normalize imported file without raw JSON.")
    data = json.loads(value)
    if not isinstance(data, dict):
        raise ValueError("Imported file raw JSON must be an object.")
    return data


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _content_hash(raw_json: str) -> str:
    return sha256(raw_json.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DomainNormalizationResult:
    status: str
    counts: dict[str, int]
    reason_codes: list[str] = field(default_factory=list)
    unresolved_references: list[dict[str, str]] = field(default_factory=list)


class DomainNormalizationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def clear_run_domain_rows(self, run_id: str) -> None:
        imported_file_ids = [
            imported_file.id
            for imported_file in self.session.exec(select(ImportedFile).where(ImportedFile.run_id == run_id)).all()
            if imported_file.id is not None
        ]
        if not imported_file_ids:
            return

        generated_gate_intent_ids = [
            intent_id
            for intent_id in self.session.exec(select(SendIntent.intent_id).where(SendIntent.run_id == run_id)).all()
            if intent_id is not None
        ]
        for model in (
            ImportedGateResult,
            SendIntent,
            EmailDraft,
            FitEvaluation,
            Contact,
            Company,
            PolicySnapshot,
            MasterCvProfileSnapshot,
            UserProfileSnapshot,
        ):
            for record in self.session.exec(select(model).where(col(model.imported_file_id).in_(imported_file_ids))).all():
                self.session.delete(record)
        for gate_result in self.session.exec(
            select(ImportedGateResult).where(
                ImportedGateResult.imported_file_id.is_(None),
                col(ImportedGateResult.external_intent_id).in_(generated_gate_intent_ids),
            )
        ).all():
            self.session.delete(gate_result)
        self.session.flush()

    def normalize_run(self, run_id: str) -> DomainNormalizationResult:
        files = {
            imported_file.filename: imported_file
            for imported_file in self.session.exec(
                select(ImportedFile).where(
                    ImportedFile.run_id == run_id,
                    ImportedFile.status == "schema_validation_passed",
                )
            ).all()
        }

        payloads = {filename: _json_loads(imported_file.raw_json) for filename, imported_file in files.items()}
        counts = {
            "user_profile_snapshots": 0,
            "master_cv_profile_snapshots": 0,
            "policy_snapshots": 0,
            "companies": 0,
            "contacts": 0,
            "fit_evaluations": 0,
            "email_drafts": 0,
            "send_intents": 0,
            "imported_gate_results": 0,
        }
        unresolved: list[dict[str, str]] = []

        user_profile = None
        if "user_profile.json" in files:
            user_profile = self._normalize_user_profile(files["user_profile.json"], payloads["user_profile.json"])
            self.session.add(user_profile)
            self.session.flush()
            counts["user_profile_snapshots"] += 1

        master_cv_profile = None
        if "master_cv_profile.json" in files:
            master_cv_profile = self._normalize_master_cv_profile(
                files["master_cv_profile.json"],
                payloads["master_cv_profile.json"],
            )
            self.session.add(master_cv_profile)
            self.session.flush()
            counts["master_cv_profile_snapshots"] += 1

        policy = None
        if "policy.json" in files:
            policy = self._normalize_policy(files["policy.json"], payloads["policy.json"])
            self.session.add(policy)
            self.session.flush()
            counts["policy_snapshots"] += 1

        full_run_files = {
            "company_candidate.json",
            "contact_candidate.json",
            "fit_evaluation.json",
            "email_draft.json",
            "send_intent.json",
            "gate_result.json",
        }
        if not full_run_files.issubset(files):
            companies_by_external_id: dict[str, Company] = {}
            if "company_candidate.json" in files:
                company = self._normalize_company(files["company_candidate.json"], payloads["company_candidate.json"])
                self.session.add(company)
                self.session.flush()
                counts["companies"] += 1
                companies_by_external_id[company.company_id] = company

            if "fit_evaluation.json" in files:
                fit_payload = payloads["fit_evaluation.json"]
                fit_company = companies_by_external_id.get(fit_payload["company_id"])
                if fit_company is None:
                    unresolved.append({"entity": fit_payload["evaluation_id"], "field": "company_id", "value": fit_payload["company_id"]})
                approved_user_profile = user_profile or self._approved_user_profile(fit_payload["profile_id"])
                approved_policy = policy or self._approved_policy(fit_payload["policy_id"])
                fit_evaluation = self._normalize_fit_evaluation(
                    files["fit_evaluation.json"],
                    fit_payload,
                    company=fit_company,
                    user_profile=approved_user_profile,
                    policy=approved_policy,
                )
                if fit_evaluation.user_profile_snapshot_id is None:
                    unresolved.append({"entity": fit_payload["evaluation_id"], "field": "profile_id", "value": fit_payload["profile_id"]})
                if fit_evaluation.policy_snapshot_id is None:
                    unresolved.append({"entity": fit_payload["evaluation_id"], "field": "policy_id", "value": fit_payload["policy_id"]})
                self.session.add(fit_evaluation)
                counts["fit_evaluations"] += 1

            reason_codes = ["unresolved_references_present"] if unresolved else []
            status = "domain_normalized_with_review" if unresolved else "domain_normalized"
            self._audit(
                run_id=run_id,
                action="domain_normalization_completed",
                result_status=status,
                reason_codes=reason_codes,
                metadata={"counts": counts, "unresolved_references": unresolved},
            )
            self.session.flush()
            return DomainNormalizationResult(
                status=status,
                counts=counts,
                reason_codes=reason_codes,
                unresolved_references=unresolved,
            )

        company = self._normalize_company(files["company_candidate.json"], payloads["company_candidate.json"])
        self.session.add(company)
        self.session.flush()
        counts["companies"] += 1
        companies_by_external_id = {company.company_id: company}

        contact_payload = payloads["contact_candidate.json"]
        contact_company = companies_by_external_id.get(contact_payload["company_id"])
        if contact_company is None:
            unresolved.append({"entity": contact_payload["contact_id"], "field": "company_id"})
        contact = self._normalize_contact(
            files["contact_candidate.json"],
            contact_payload,
            company=contact_company,
        )
        self.session.add(contact)
        self.session.flush()
        counts["contacts"] += 1
        contacts_by_external_id = {contact.contact_id: contact}

        fit_payload = payloads["fit_evaluation.json"]
        fit_company = companies_by_external_id.get(fit_payload["company_id"])
        if fit_company is None:
            unresolved.append({"entity": fit_payload["evaluation_id"], "field": "company_id"})
        fit_evaluation = self._normalize_fit_evaluation(
            files["fit_evaluation.json"],
            fit_payload,
            company=fit_company,
            user_profile=user_profile if user_profile is not None and fit_payload["profile_id"] == user_profile.profile_id else None,
            policy=policy if policy is not None and fit_payload["policy_id"] == policy.policy_id else None,
        )
        if fit_evaluation.user_profile_snapshot_id is None:
            unresolved.append({"entity": fit_payload["evaluation_id"], "field": "profile_id"})
        if fit_evaluation.policy_snapshot_id is None:
            unresolved.append({"entity": fit_payload["evaluation_id"], "field": "policy_id"})
        self.session.add(fit_evaluation)
        counts["fit_evaluations"] += 1

        draft_payload = payloads["email_draft.json"]
        draft_company = companies_by_external_id.get(draft_payload["company_id"])
        draft_contact = contacts_by_external_id.get(draft_payload["contact_id"])
        if draft_company is None:
            unresolved.append({"entity": draft_payload["draft_id"], "field": "company_id"})
        if draft_contact is None:
            unresolved.append({"entity": draft_payload["draft_id"], "field": "contact_id"})
        email_draft = self._normalize_email_draft(
            files["email_draft.json"],
            draft_payload,
            company=draft_company,
            contact=draft_contact,
        )
        self.session.add(email_draft)
        self.session.flush()
        counts["email_drafts"] += 1
        drafts_by_external_id = {email_draft.draft_id: email_draft}

        intent_payload = payloads["send_intent.json"]
        intent_company = companies_by_external_id.get(intent_payload["company_id"])
        intent_contact = contacts_by_external_id.get(intent_payload["contact_id"])
        intent_draft = drafts_by_external_id.get(intent_payload["email_draft_id"])
        for field_name, value, found in (
            ("company_id", intent_payload["company_id"], intent_company),
            ("contact_id", intent_payload["contact_id"], intent_contact),
            ("email_draft_id", intent_payload["email_draft_id"], intent_draft),
            ("policy_id", intent_payload["policy_id"], policy if policy is not None and intent_payload["policy_id"] == policy.policy_id else None),
            (
                "profile_id",
                intent_payload["profile_id"],
                user_profile if user_profile is not None and intent_payload["profile_id"] == user_profile.profile_id else None,
            ),
            (
                "master_cv_profile_id",
                intent_payload["master_cv_profile_id"],
                master_cv_profile
                if master_cv_profile is not None and intent_payload["master_cv_profile_id"] == master_cv_profile.profile_id
                else None,
            ),
        ):
            if found is None:
                unresolved.append({"entity": intent_payload["intent_id"], "field": field_name, "value": value})
        send_intent = self._normalize_send_intent(
            files["send_intent.json"],
            intent_payload,
            run_id=run_id,
            company=intent_company,
            contact=intent_contact,
            email_draft=intent_draft,
            policy=policy if policy is not None and intent_payload["policy_id"] == policy.policy_id else None,
            user_profile=user_profile if user_profile is not None and intent_payload["profile_id"] == user_profile.profile_id else None,
            master_cv_profile=master_cv_profile
            if master_cv_profile is not None and intent_payload["master_cv_profile_id"] == master_cv_profile.profile_id
            else None,
        )
        if unresolved:
            send_intent.status = "needs_review"
        self.session.add(send_intent)
        self.session.flush()
        counts["send_intents"] += 1

        gate_payload = payloads["gate_result.json"]
        gate_result = self._normalize_gate_result(
            files["gate_result.json"],
            gate_payload,
            send_intent=send_intent if gate_payload["intent_id"] == send_intent.intent_id else None,
            policy=policy if policy is not None and gate_payload.get("policy_snapshot_id") == policy.policy_id else None,
        )
        if gate_result.send_intent_id is None:
            unresolved.append({"entity": gate_payload["gate_result_id"], "field": "intent_id"})
        self.session.add(gate_result)
        counts["imported_gate_results"] += 1

        reason_codes = ["unresolved_references_present"] if unresolved else []
        status = "domain_normalized_with_review" if unresolved else "domain_normalized"
        self._audit(
            run_id=run_id,
            action="domain_normalization_completed",
            result_status=status,
            reason_codes=reason_codes,
            metadata={"counts": counts, "unresolved_references": unresolved},
        )
        self.session.flush()
        return DomainNormalizationResult(
            status=status,
            counts=counts,
            reason_codes=reason_codes,
            unresolved_references=unresolved,
        )

    def _normalize_user_profile(self, imported_file: ImportedFile, data: dict[str, Any]) -> UserProfileSnapshot:
        raw_json = imported_file.raw_json or _json_dumps(data)
        return UserProfileSnapshot(
            profile_id=data["profile_id"],
            schema_version=data["schema_version"],
            source_created_at=_parse_datetime(data.get("created_at")),
            source_updated_at=_parse_datetime(data.get("updated_at")),
            content_hash=_content_hash(raw_json),
            status=SNAPSHOT_STATUS_CANDIDATE,
            raw_json=raw_json,
            imported_file_id=imported_file.id,
        )

    def _approved_user_profile(self, profile_id: str) -> UserProfileSnapshot | None:
        return self.session.exec(
            select(UserProfileSnapshot).where(
                UserProfileSnapshot.profile_id == profile_id,
                UserProfileSnapshot.status == "approved",
            )
        ).first()

    def _approved_policy(self, policy_id: str) -> PolicySnapshot | None:
        return self.session.exec(
            select(PolicySnapshot).where(
                PolicySnapshot.policy_id == policy_id,
                PolicySnapshot.status == "approved",
            )
        ).first()

    def _normalize_master_cv_profile(self, imported_file: ImportedFile, data: dict[str, Any]) -> MasterCvProfileSnapshot:
        raw_json = imported_file.raw_json or _json_dumps(data)
        return MasterCvProfileSnapshot(
            profile_id=data["profile_id"],
            schema_version=data["schema_version"],
            source_created_at=_parse_datetime(data.get("created_at")),
            content_hash=_content_hash(raw_json),
            status=SNAPSHOT_STATUS_CANDIDATE,
            raw_json=raw_json,
            imported_file_id=imported_file.id,
        )

    def _normalize_policy(self, imported_file: ImportedFile, data: dict[str, Any]) -> PolicySnapshot:
        raw_json = imported_file.raw_json or _json_dumps(data)
        return PolicySnapshot(
            policy_id=data["policy_id"],
            schema_version=data["schema_version"],
            source_created_at=_parse_datetime(data.get("created_at")),
            content_hash=_content_hash(raw_json),
            status=SNAPSHOT_STATUS_CANDIDATE,
            raw_json=raw_json,
            imported_file_id=imported_file.id,
        )

    def _normalize_company(self, imported_file: ImportedFile, data: dict[str, Any]) -> Company:
        normalized_domain = normalize_company_domain(data.get("domain"))
        normalized_name = normalize_company_name(data["name"])
        company_policy_key, company_policy_key_kind = build_company_policy_key(
            normalized_domain=normalized_domain,
            normalized_name=normalized_name,
        )
        return Company(
            company_id=data["company_id"],
            name=data["name"],
            raw_domain=data.get("domain"),
            normalized_domain=normalized_domain,
            normalized_name=normalized_name,
            company_policy_key=company_policy_key,
            company_policy_key_kind=company_policy_key_kind,
            description=data.get("description"),
            industry_tags_json=_json_dumps(data.get("industry_tags") or []),
            locations_json=_json_dumps(data.get("locations") or []),
            remote_policy=data.get("remote_policy"),
            source_refs_json=_json_dumps(data["source_refs"]),
            confidence=data["confidence"],
            review_flags_json=_json_dumps(data["review_flags"]),
            policy_conflicts_json=_json_dumps(data.get("potential_policy_conflicts") or []),
            raw_json=imported_file.raw_json or _json_dumps(data),
            imported_file_id=imported_file.id,
        )

    def _normalize_contact(self, imported_file: ImportedFile, data: dict[str, Any], *, company: Company | None) -> Contact:
        return Contact(
            contact_id=data["contact_id"],
            company_id=company.id if company is not None else None,
            external_company_id=data["company_id"],
            name=data.get("name"),
            role_title=data.get("role_title"),
            raw_email=data["email"],
            normalized_recipient_email=normalize_recipient_email(data["email"]),
            email_source=data["email_source"],
            profile_url=data.get("profile_url"),
            source_refs_json=_json_dumps(data["source_refs"]),
            confidence=data["confidence"],
            review_flags_json=_json_dumps(data["review_flags"]),
            raw_json=imported_file.raw_json or _json_dumps(data),
            imported_file_id=imported_file.id,
        )

    def _normalize_fit_evaluation(
        self,
        imported_file: ImportedFile,
        data: dict[str, Any],
        *,
        company: Company | None,
        user_profile: UserProfileSnapshot | None,
        policy: PolicySnapshot | None,
    ) -> FitEvaluation:
        return FitEvaluation(
            evaluation_id=data["evaluation_id"],
            company_id=company.id if company is not None else None,
            external_company_id=data["company_id"],
            user_profile_snapshot_id=user_profile.id if user_profile is not None else None,
            policy_snapshot_id=policy.id if policy is not None else None,
            fit_score=data["fit_score"],
            decision=data["decision"],
            reasons_json=_json_dumps(data["reasons"]),
            risks_json=_json_dumps(data["risks"]),
            source_refs_json=_json_dumps(data["source_refs"]),
            confidence=data["confidence"],
            review_flags_json=_json_dumps(data["review_flags"]),
            raw_json=imported_file.raw_json or _json_dumps(data),
            imported_file_id=imported_file.id,
        )

    def _normalize_email_draft(
        self,
        imported_file: ImportedFile,
        data: dict[str, Any],
        *,
        company: Company | None,
        contact: Contact | None,
    ) -> EmailDraft:
        return EmailDraft(
            draft_id=data["draft_id"],
            company_id=company.id if company is not None else None,
            external_company_id=data["company_id"],
            contact_id=contact.id if contact is not None else None,
            external_contact_id=data["contact_id"],
            subject=data["subject"],
            body_text=data["body_text"],
            body_html=data.get("body_html"),
            tone=data.get("tone"),
            claim_refs_json=_json_dumps(data["claim_refs"]),
            source_refs_json=_json_dumps(data["source_refs"]),
            attachments_json=_json_dumps(data.get("attachments") or []),
            confidence=data["confidence"],
            review_flags_json=_json_dumps(data["review_flags"]),
            raw_json=imported_file.raw_json or _json_dumps(data),
            imported_file_id=imported_file.id,
        )

    def _normalize_send_intent(
        self,
        imported_file: ImportedFile,
        data: dict[str, Any],
        *,
        run_id: str,
        company: Company | None,
        contact: Contact | None,
        email_draft: EmailDraft | None,
        policy: PolicySnapshot | None,
        user_profile: UserProfileSnapshot | None,
        master_cv_profile: MasterCvProfileSnapshot | None,
    ) -> SendIntent:
        return SendIntent(
            intent_id=data["intent_id"],
            run_id=run_id,
            company_id=company.id if company is not None else None,
            external_company_id=data["company_id"],
            contact_id=contact.id if contact is not None else None,
            external_contact_id=data["contact_id"],
            email_draft_id=email_draft.id if email_draft is not None else None,
            external_email_draft_id=data["email_draft_id"],
            raw_recipient_email=data["recipient_email"],
            normalized_recipient_email=normalize_recipient_email(data["recipient_email"]),
            recipient_name=data.get("recipient_name"),
            company_domain=data.get("company_domain"),
            subject=data["subject"],
            body_text=data["body_text"],
            body_html=data.get("body_html"),
            attachments_json=_json_dumps(data["attachments"]),
            source_refs_json=_json_dumps(data["source_refs"]),
            claim_refs_json=_json_dumps(data.get("claim_refs") or []),
            policy_snapshot_id=policy.id if policy is not None else None,
            external_policy_id=data["policy_id"],
            user_profile_snapshot_id=user_profile.id if user_profile is not None else None,
            external_profile_id=data["profile_id"],
            master_cv_profile_snapshot_id=master_cv_profile.id if master_cv_profile is not None else None,
            external_master_cv_profile_id=data["master_cv_profile_id"],
            confidence=data["confidence"],
            review_flags_json=_json_dumps(data["review_flags"]),
            created_by=data["created_by"],
            status="imported",
            raw_json=imported_file.raw_json or _json_dumps(data),
            imported_file_id=imported_file.id,
        )

    def _normalize_gate_result(
        self,
        imported_file: ImportedFile,
        data: dict[str, Any],
        *,
        send_intent: SendIntent | None,
        policy: PolicySnapshot | None,
    ) -> ImportedGateResult:
        return ImportedGateResult(
            gate_result_id=data["gate_result_id"],
            send_intent_id=send_intent.id if send_intent is not None else None,
            external_intent_id=data["intent_id"],
            status=data["status"],
            checks_json=_json_dumps(data["checks"]),
            reasons_json=_json_dumps(data["reasons"]),
            external_reservation_id=data.get("reservation_id"),
            evaluated_at=_parse_datetime(data["evaluated_at"]) or datetime.now(),
            policy_snapshot_id=policy.id if policy is not None else None,
            external_policy_id=data.get("policy_snapshot_id"),
            raw_json=imported_file.raw_json or _json_dumps(data),
            imported_file_id=imported_file.id,
        )

    def _audit(
        self,
        *,
        run_id: str,
        action: str,
        result_status: str,
        reason_codes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                run_id=run_id,
                actor_type="backend",
                action=action,
                entity_type="domain_normalization",
                entity_id=run_id,
                result_status=result_status,
                reason_codes_json=_json_dumps(reason_codes or []),
                metadata_json=_json_dumps(metadata or {}),
            )
        )
