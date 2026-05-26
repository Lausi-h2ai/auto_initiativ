from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from jsonschema.exceptions import ValidationError
from sqlmodel import Session, select

from backend.app.db.models import (
    AuditLog,
    Company,
    Contact,
    EmailDraft,
    FitEvaluation,
    ImportedGateResult,
    MasterCvProfileSnapshot,
    OutreachRecord,
    PolicySnapshot,
    SendIntent,
    UserProfileSnapshot,
    utc_now,
)
from backend.app.db.normalization import normalize_company_domain, normalize_company_name
from backend.app.imports.schema_registry import SchemaRegistry
from backend.app.onboarding.promotion import SNAPSHOT_STATUS_APPROVED


CONTACTED_OUTREACH_STATUSES = {"sent", "provider_accepted", "outcome_uncertain"}
DEFAULT_DEDUPE_WINDOW_DAYS = 365
SAFE_EMAIL_SOURCES = {"company_site", "public_profile"}
REVIEW_EMAIL_SOURCES = {"user_provided", "inferred_pattern", "other"}


@dataclass(frozen=True)
class GateEvaluation:
    gate_result: ImportedGateResult
    checks: list[dict[str, str]]
    reasons: list[dict[str, str]]
    raw_result: dict[str, Any]


@dataclass
class _GateState:
    checks: list[dict[str, str]] = field(default_factory=list)
    reasons: list[dict[str, str]] = field(default_factory=list)

    def pass_check(self, code: str, details: str) -> None:
        self.checks.append({"code": code, "status": "pass", "details": details})

    def fail_check(self, code: str, message: str, *, field: str | None = None) -> None:
        self.checks.append({"code": code, "status": "fail", "details": message})
        self.reasons.append(_reason(code, message, field=field))

    def warn_check(self, code: str, message: str, *, field: str | None = None) -> None:
        self.checks.append({"code": code, "status": "warning", "details": message})
        self.reasons.append(_reason(code, message, field=field))


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _json_loads(value: str | None) -> dict[str, Any]:
    if value is None:
        return {}
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _json_list(value: str | None) -> list[Any]:
    if value is None:
        return []
    try:
        data = json.loads(value)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _reason(code: str, message: str, *, field: str | None = None) -> dict[str, str]:
    reason = {"code": code, "message": message}
    if field is not None:
        reason["field"] = field
    return reason


def _json_path(error: ValidationError) -> str:
    if not error.absolute_path:
        return "$"
    return "$." + ".".join(str(part) for part in error.absolute_path)


def _validation_reason_code(error: ValidationError) -> str:
    if error.validator == "required":
        return "schema_missing_required_field"
    if error.validator == "additionalProperties":
        return "schema_additional_property"
    if error.validator == "enum":
        return "schema_invalid_enum"
    if error.validator == "format":
        return f"schema_invalid_{error.validator_value}"
    return "schema_validation_failed"


def _parse_dt(value: datetime | str | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _contains_forbidden_claim(text: str, forbidden_claims: list[str]) -> str | None:
    haystack = text.casefold()
    for claim in forbidden_claims:
        normalized = claim.strip().casefold()
        if normalized and normalized in haystack:
            return claim
    return None


class EvaluateOnlyGateService:
    def __init__(self, session: Session, registry: SchemaRegistry | None = None) -> None:
        self.session = session
        self.registry = registry or SchemaRegistry()

    def evaluate(self, intent_id: str) -> GateEvaluation:
        intent = self.session.exec(select(SendIntent).where(SendIntent.intent_id == intent_id)).first()
        if intent is None:
            raise ValueError(f"Send intent not found: {intent_id}")

        self._audit(
            run_id=intent.run_id,
            action="gate_evaluation_started",
            entity_id=intent.intent_id,
            result_status="started",
            metadata={
                "mode": "evaluate_only",
                "policy_snapshot_id": intent.external_policy_id,
                "send_intent_id": intent.intent_id,
            },
        )

        state = _GateState()
        related = self._load_related(intent)
        self._check_schema(intent, state)
        policy_payload = self._check_policy(intent, related["policy"], state)
        master_cv_payload = self._check_required_records(intent, related, state)
        self._check_snapshot_statuses(related, state)
        self._check_dedupe(intent, related["company"], policy_payload, state)
        self._check_policy_exclusions(intent, related["company"], policy_payload, state)
        self._check_sources_and_attachments(intent, related["email_draft"], state)
        self._check_limits(policy_payload, state)
        self._check_claims(intent, related["email_draft"], master_cv_payload, policy_payload, state)
        self._check_confidence_and_review_flags(intent, related, policy_payload, state)
        self._check_contact_safety(related["contact"], state)

        status = self._status_from_checks(state.checks)
        raw_result = {
            "schema_version": "1.0",
            "gate_result_id": self._gate_result_id(intent.intent_id),
            "intent_id": intent.intent_id,
            "status": status,
            "checks": state.checks,
            "reasons": state.reasons,
            "evaluated_at": utc_now().isoformat(),
            "policy_snapshot_id": intent.external_policy_id,
        }

        gate_result = self._upsert_gate_result(intent, related["policy"], raw_result)
        self._audit(
            run_id=intent.run_id,
            action="gate_evaluation_completed",
            entity_id=intent.intent_id,
            result_status=status,
            reason_codes=[reason["code"] for reason in state.reasons],
            metadata={
                "mode": "evaluate_only",
                "gate_result_id": gate_result.gate_result_id,
                "check_count": len(state.checks),
                "reason_count": len(state.reasons),
            },
        )
        self.session.flush()
        return GateEvaluation(gate_result=gate_result, checks=state.checks, reasons=state.reasons, raw_result=raw_result)

    def _load_related(self, intent: SendIntent) -> dict[str, Any]:
        return {
            "company": self.session.get(Company, intent.company_id) if intent.company_id is not None else None,
            "contact": self.session.get(Contact, intent.contact_id) if intent.contact_id is not None else None,
            "email_draft": self.session.get(EmailDraft, intent.email_draft_id) if intent.email_draft_id is not None else None,
            "policy": self.session.get(PolicySnapshot, intent.policy_snapshot_id) if intent.policy_snapshot_id is not None else None,
            "user_profile": self.session.get(UserProfileSnapshot, intent.user_profile_snapshot_id)
            if intent.user_profile_snapshot_id is not None
            else None,
            "master_cv_profile": self.session.get(MasterCvProfileSnapshot, intent.master_cv_profile_snapshot_id)
            if intent.master_cv_profile_snapshot_id is not None
            else None,
            "fit_evaluation": self.session.exec(
                select(FitEvaluation).where(FitEvaluation.company_id == intent.company_id).order_by(FitEvaluation.created_at.desc())
            ).first()
            if intent.company_id is not None
            else None,
        }

    def _check_schema(self, intent: SendIntent, state: _GateState) -> None:
        if not intent.raw_json:
            state.fail_check("schema_validity", "Send intent raw JSON is missing.", field="raw_json")
            return

        try:
            payload = json.loads(intent.raw_json)
        except json.JSONDecodeError as exc:
            state.fail_check("schema_invalid_json", exc.msg, field="raw_json")
            return

        validator = self.registry.get_validator("send_intent.schema.json")
        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.absolute_path))
        if not errors:
            state.pass_check("schema_validity", "Send intent raw JSON validates against schema.")
            return

        for error in errors:
            state.fail_check(_validation_reason_code(error), error.message, field=_json_path(error))

    def _check_policy(self, intent: SendIntent, policy: PolicySnapshot | None, state: _GateState) -> dict[str, Any]:
        if policy is None:
            state.fail_check("policy_missing", "Policy snapshot could not be resolved.", field="policy_id")
            return {}
        if policy.policy_id != intent.external_policy_id:
            state.fail_check("policy_mismatch", "Policy snapshot does not match send intent.", field="policy_id")
        else:
            state.pass_check("policy_loaded", "Policy snapshot resolved.")
        return _json_loads(policy.raw_json)

    def _check_required_records(self, intent: SendIntent, related: dict[str, Any], state: _GateState) -> dict[str, Any]:
        required = {
            "company_id": related["company"],
            "contact_id": related["contact"],
            "email_draft_id": related["email_draft"],
            "profile_id": related["user_profile"],
            "master_cv_profile_id": related["master_cv_profile"],
        }
        for field_name, record in required.items():
            if record is None:
                state.fail_check("required_record_missing", f"Required record for {field_name} could not be resolved.", field=field_name)

        if all(record is not None for record in required.values()):
            state.pass_check("required_records_present", "All required linked records resolved.")

        master_cv = related["master_cv_profile"]
        return _json_loads(master_cv.raw_json) if master_cv is not None else {}

    def _check_snapshot_statuses(self, related: dict[str, Any], state: _GateState) -> None:
        snapshots = {
            "policy_id": related["policy"],
            "profile_id": related["user_profile"],
            "master_cv_profile_id": related["master_cv_profile"],
        }
        blocked: list[str] = []
        for field_name, snapshot in snapshots.items():
            if snapshot is not None and snapshot.status != SNAPSHOT_STATUS_APPROVED:
                blocked.append(field_name)
                state.fail_check(
                    "snapshot_not_approved",
                    "Linked onboarding snapshot is not approved for automated use.",
                    field=field_name,
                )
        if not blocked and all(snapshot is not None for snapshot in snapshots.values()):
            state.pass_check("snapshots_approved", "Linked onboarding snapshots are approved.")

    def _check_dedupe(self, intent: SendIntent, company: Company | None, policy: dict[str, Any], state: _GateState) -> None:
        outreach_policy = policy.get("outreach", {})
        if not outreach_policy.get("allow_recipient_repeat", False):
            recipient_window_days = int(outreach_policy.get("recipient_dedupe_window_days") or DEFAULT_DEDUPE_WINDOW_DAYS)
            recipient_cutoff = utc_now() - timedelta(days=recipient_window_days)
            duplicate = self.session.exec(
                select(OutreachRecord).where(
                    OutreachRecord.normalized_recipient_email == intent.normalized_recipient_email,
                    OutreachRecord.status.in_(CONTACTED_OUTREACH_STATUSES),
                    OutreachRecord.dedupe_recipient == True,  # noqa: E712
                    OutreachRecord.occurred_at >= recipient_cutoff,
                )
            ).first()
            if duplicate is not None:
                state.fail_check("duplicate_recipient", "Recipient was already contacted inside the dedupe window.", field="recipient_email")
            else:
                state.pass_check("recipient_not_previously_contacted", "Recipient dedupe check passed.")
        else:
            state.pass_check("recipient_repeat_allowed", "Policy allows recipient repeat outreach.")

        if not outreach_policy.get("allow_company_repeat", False):
            company_key = company.company_policy_key if company is not None else None
            company_window_days = int(outreach_policy.get("company_dedupe_window_days") or DEFAULT_DEDUPE_WINDOW_DAYS)
            company_cutoff = utc_now() - timedelta(days=company_window_days)
            duplicate = (
                self.session.exec(
                    select(OutreachRecord).where(
                        OutreachRecord.company_policy_key == company_key,
                        OutreachRecord.status.in_(CONTACTED_OUTREACH_STATUSES),
                        OutreachRecord.dedupe_company == True,  # noqa: E712
                        OutreachRecord.occurred_at >= company_cutoff,
                    )
                ).first()
                if company_key
                else None
            )
            if duplicate is not None:
                state.fail_check("duplicate_company", "Company was already contacted inside the dedupe window.", field="company_id")
            elif company_key:
                state.pass_check("company_not_previously_contacted", "Company dedupe check passed.")
        else:
            state.pass_check("company_repeat_allowed", "Policy allows company repeat outreach.")

    def _check_policy_exclusions(self, intent: SendIntent, company: Company | None, policy: dict[str, Any], state: _GateState) -> None:
        exclusions = policy.get("exclusions", {})
        blocked_domains = {
            domain
            for domain in (normalize_company_domain(item.get("value")) for item in exclusions.get("domains", []))
            if domain is not None
        }
        intent_domain = normalize_company_domain(intent.company_domain)
        company_domain = company.normalized_domain if company is not None else None
        if (intent_domain and intent_domain in blocked_domains) or (company_domain and company_domain in blocked_domains):
            state.fail_check("blocked_domain", "Company domain is blocked by policy.", field="company_domain")
        else:
            state.pass_check("domain_not_blocked", "Company domain is not blocked.")

        blocked_names = {normalize_company_name(item["value"]) for item in exclusions.get("company_names", [])}
        if company is not None and company.normalized_name in blocked_names:
            state.fail_check("blocked_company", "Company name is blocked by policy.", field="company_id")
        else:
            state.pass_check("company_not_blocked", "Company name is not blocked.")

        text = f"{intent.subject}\n{intent.body_text}".casefold()
        for item in exclusions.get("keywords", []):
            keyword = item["value"].strip().casefold()
            if keyword and keyword in text:
                state.fail_check("blocked_keyword", "Send intent contains a policy-blocked keyword.", field="body_text")
                return
        state.pass_check("policy_keywords_clear", "No policy-blocked keyword found.")

    def _check_sources_and_attachments(self, intent: SendIntent, email_draft: EmailDraft | None, state: _GateState) -> None:
        source_refs = _json_list(intent.source_refs_json)
        if source_refs:
            state.pass_check("source_refs_present", "Send intent has source references.")
        else:
            state.fail_check("source_refs_missing", "Send intent has no source references.", field="source_refs")

        if email_draft is not None:
            draft_source_refs = _json_list(email_draft.source_refs_json)
            if not set(source_refs).issubset(set(draft_source_refs)):
                state.fail_check("source_refs_not_in_draft", "Some send intent source refs are not present on the email draft.", field="source_refs")

        attachments = _json_list(intent.attachments_json)
        missing = [
            attachment.get("attachment_id", attachment.get("path", "unknown"))
            for attachment in attachments
            if not attachment.get("exists_at_draft_time", False)
        ]
        if missing:
            state.fail_check("attachments_missing", "One or more attachments were missing at draft time.", field="attachments")
        else:
            state.pass_check("attachments_exist", "All send intent attachments existed at draft time.")

    def _check_limits(self, policy: dict[str, Any], state: _GateState) -> None:
        limits = policy.get("limits", {})
        daily_limit = limits.get("daily_send_limit")
        weekly_limit = limits.get("weekly_send_limit")
        if daily_limit is None or weekly_limit is None:
            state.fail_check("send_limits_missing", "Daily or weekly send limit is missing.", field="limits")
            return

        now = utc_now()
        day_start = now - timedelta(days=1)
        week_start = now - timedelta(days=7)
        contacted = select(OutreachRecord).where(OutreachRecord.status.in_(CONTACTED_OUTREACH_STATUSES))
        daily_count = sum(1 for record in self.session.exec(contacted).all() if (_parse_dt(record.occurred_at) or now) >= day_start)
        weekly_count = sum(1 for record in self.session.exec(contacted).all() if (_parse_dt(record.occurred_at) or now) >= week_start)

        if daily_count >= daily_limit:
            state.fail_check("daily_limit_reached", "Daily send limit has been reached.", field="limits.daily_send_limit")
        elif weekly_count >= weekly_limit:
            state.fail_check("weekly_limit_reached", "Weekly send limit has been reached.", field="limits.weekly_send_limit")
        else:
            state.pass_check("send_limits_available", "Daily and weekly send limits are available.")

    def _check_claims(
        self,
        intent: SendIntent,
        email_draft: EmailDraft | None,
        master_cv: dict[str, Any],
        policy: dict[str, Any],
        state: _GateState,
    ) -> None:
        approved_claim_ids = {
            claim["claim_id"] for claim in master_cv.get("claims", []) if claim.get("approved_for_tailoring") is True
        }
        intent_claim_refs = set(_json_list(intent.claim_refs_json))
        draft_claim_refs = set(_json_list(email_draft.claim_refs_json)) if email_draft is not None else set()
        unknown_claims = sorted((intent_claim_refs | draft_claim_refs) - approved_claim_ids)
        if unknown_claims:
            state.fail_check("unapproved_claim_refs", "Claim references are missing or not approved for tailoring.", field="claim_refs")
        else:
            state.pass_check("claim_refs_approved", "All claim references are approved for tailoring.")

        forbidden_claim = _contains_forbidden_claim(f"{intent.subject}\n{intent.body_text}", policy.get("forbidden_claims", []))
        if forbidden_claim is not None:
            state.fail_check("forbidden_claim_present", "Send intent contains a forbidden claim.", field="body_text")
        else:
            state.pass_check("forbidden_claims_clear", "No forbidden claims found.")

    def _check_confidence_and_review_flags(self, intent: SendIntent, related: dict[str, Any], policy: dict[str, Any], state: _GateState) -> None:
        thresholds = policy.get("review_thresholds", {})
        minimum_confidence = thresholds.get("minimum_required_confidence")
        if minimum_confidence is None:
            state.fail_check("confidence_threshold_missing", "Minimum confidence threshold is missing.", field="review_thresholds")
            return

        confidence_records = {
            "send_intent": intent.confidence,
            "company": related["company"].confidence if related["company"] is not None else None,
            "contact": related["contact"].confidence if related["contact"] is not None else None,
            "email_draft": related["email_draft"].confidence if related["email_draft"] is not None else None,
            "fit_evaluation": related["fit_evaluation"].confidence if related["fit_evaluation"] is not None else None,
        }
        low_confidence = [name for name, confidence in confidence_records.items() if confidence is not None and confidence < minimum_confidence]
        if low_confidence:
            state.fail_check("low_confidence_required_field", "One or more required records are below the confidence threshold.", field="confidence")
        else:
            state.pass_check("confidence_threshold_met", "Required records meet confidence threshold.")

        if thresholds.get("block_needs_review_required_fields", True):
            flagged = [
                name
                for name, record in related.items()
                if hasattr(record, "review_flags_json") and _json_list(record.review_flags_json)
            ]
            if _json_list(intent.review_flags_json):
                flagged.append("send_intent")
            if flagged:
                state.fail_check("review_flags_present", "Required records contain review flags.", field="review_flags")
            else:
                state.pass_check("review_flags_clear", "No required review flags found.")
        elif _json_list(intent.review_flags_json):
            state.warn_check("review_flags_present", "Send intent contains review flags.", field="review_flags")

    def _check_contact_safety(self, contact: Contact | None, state: _GateState) -> None:
        if contact is None:
            return
        if contact.email_source in SAFE_EMAIL_SOURCES:
            state.pass_check("contact_email_source_safe", "Contact email source is acceptable.")
        elif contact.email_source in REVIEW_EMAIL_SOURCES:
            state.warn_check("contact_email_needs_review", "Contact email source requires review.", field="email_source")
        else:
            state.fail_check("contact_email_source_unknown", "Contact email source is unknown.", field="email_source")

    def _status_from_checks(self, checks: list[dict[str, str]]) -> str:
        statuses = {check["status"] for check in checks}
        if "fail" in statuses:
            return "blocked"
        if "warning" in statuses:
            return "needs_review"
        return "passed_evaluate_only"

    def _upsert_gate_result(
        self,
        intent: SendIntent,
        policy: PolicySnapshot | None,
        raw_result: dict[str, Any],
    ) -> ImportedGateResult:
        gate_result_id = raw_result["gate_result_id"]
        existing = self.session.exec(select(ImportedGateResult).where(ImportedGateResult.gate_result_id == gate_result_id)).first()
        evaluated_at = _parse_dt(raw_result["evaluated_at"]) or utc_now()
        if existing is None:
            existing = ImportedGateResult(gate_result_id=gate_result_id, external_intent_id=intent.intent_id, evaluated_at=evaluated_at)

        existing.send_intent_id = intent.id
        existing.status = raw_result["status"]
        existing.checks_json = _json_dumps(raw_result["checks"])
        existing.reasons_json = _json_dumps(raw_result["reasons"])
        existing.external_reservation_id = None
        existing.evaluated_at = evaluated_at
        existing.policy_snapshot_id = policy.id if policy is not None else None
        existing.external_policy_id = intent.external_policy_id
        existing.raw_json = _json_dumps(raw_result)
        existing.imported_file_id = None
        self.session.add(existing)
        self.session.flush()
        return existing

    def _gate_result_id(self, intent_id: str) -> str:
        return f"gate-evaluate-only-{intent_id}"

    def _audit(
        self,
        *,
        run_id: str,
        action: str,
        entity_id: str,
        result_status: str,
        reason_codes: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.session.add(
            AuditLog(
                run_id=run_id,
                actor_type="backend",
                action=action,
                entity_type="gate_evaluation",
                entity_id=entity_id,
                result_status=result_status,
                reason_codes_json=_json_dumps(reason_codes or []),
                metadata_json=_json_dumps(metadata or {}),
            )
        )
