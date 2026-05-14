from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import AnyUrl, BaseModel, ConfigDict, EmailStr, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def reject_explicit_nulls(cls, data):
        if isinstance(data, dict):
            null_fields = sorted(key for key, value in data.items() if value is None)
            if null_fields:
                joined_fields = ", ".join(null_fields)
                raise ValueError(f"Fields may be omitted but not set to null: {joined_fields}")
        return data


class Provenance(StrictModel):
    source_type: Literal["verified_document", "user_claim", "inferred", "needs_review"]
    confidence: float = Field(ge=0, le=1)
    needs_review: bool
    source_refs: list[str]


class PolicyConflict(StrictModel):
    policy_value: str
    reason: str
    confidence: float = Field(ge=0, le=1)


class CompanyCandidate(StrictModel):
    schema_version: Literal["1.0"]
    company_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    website_url: AnyUrl | None = None
    domain: str = Field(min_length=1)
    description: str | None = None
    industry_tags: list[str] | None = None
    locations: list[str] | None = None
    remote_policy: str | None = None
    potential_policy_conflicts: list[PolicyConflict] | None = None
    source_refs: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    review_flags: list[str]


class ContactCandidate(StrictModel):
    schema_version: Literal["1.0"]
    contact_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    name: str | None = None
    role_title: str | None = None
    email: EmailStr
    email_source: Literal["company_site", "public_profile", "user_provided", "inferred_pattern", "other"]
    profile_url: AnyUrl | None = None
    confidence: float = Field(ge=0, le=1)
    source_refs: list[str] = Field(min_length=1)
    review_flags: list[str]


class EmailDraftAttachmentRef(StrictModel):
    attachment_id: str
    path: str
    kind: Literal["cv", "cover_letter", "portfolio", "other"]


class EmailDraft(StrictModel):
    schema_version: Literal["1.0"]
    draft_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    contact_id: str = Field(min_length=1)
    subject: str = Field(min_length=1)
    body_text: str = Field(min_length=1)
    body_html: str | None = None
    tone: str | None = None
    claim_refs: list[str]
    source_refs: list[str]
    attachments: list[EmailDraftAttachmentRef] | None = None
    confidence: float = Field(ge=0, le=1)
    review_flags: list[str]


class SourcedReason(StrictModel):
    text: str = Field(min_length=1)
    source_refs: list[str]


class FitEvaluation(StrictModel):
    schema_version: Literal["1.0"]
    evaluation_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    policy_id: str = Field(min_length=1)
    fit_score: float = Field(ge=0, le=1)
    decision: Literal["promising", "weak_fit", "blocked_by_policy", "needs_review"]
    reasons: list[SourcedReason]
    risks: list[SourcedReason]
    source_refs: list[str]
    confidence: float = Field(ge=0, le=1)
    review_flags: list[str]


class GateCheck(StrictModel):
    code: str = Field(min_length=1)
    status: Literal["pass", "fail", "warning", "not_applicable"]
    details: str | None = None


class GateReason(StrictModel):
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    field: str | None = None


class GateResult(StrictModel):
    schema_version: Literal["1.0"]
    gate_result_id: str = Field(min_length=1)
    intent_id: str = Field(min_length=1)
    status: Literal["passed_dry_run", "blocked", "needs_review", "reserved", "sent", "send_failed"]
    checks: list[GateCheck]
    reasons: list[GateReason]
    reservation_id: str | None = None
    evaluated_at: datetime
    policy_snapshot_id: str | None = None


class MasterCvClaim(StrictModel):
    claim_id: str = Field(min_length=1)
    category: Literal[
        "experience",
        "project",
        "education",
        "skill",
        "language",
        "certification",
        "achievement",
        "preference",
        "other",
    ]
    statement: str = Field(min_length=1)
    start_date: str | None = None
    end_date: str | None = None
    organization: str | None = None
    role: str | None = None
    tags: list[str] | None = None
    approved_for_tailoring: bool
    provenance: Provenance


class MasterCvProfile(StrictModel):
    schema_version: Literal["1.0"]
    profile_id: str = Field(min_length=1)
    created_at: datetime
    claims: list[MasterCvClaim]
    preferred_cv_sections: list[str] | None = None
    template_refs: list[str] | None = None


class PolicyItem(StrictModel):
    value: str = Field(min_length=1)
    reason: str
    provenance: Provenance


class PolicyExclusions(StrictModel):
    industries: list[PolicyItem]
    company_names: list[PolicyItem]
    domains: list[PolicyItem]
    keywords: list[PolicyItem]


class PolicyOutreach(StrictModel):
    allow_company_repeat: bool
    allow_recipient_repeat: bool
    company_dedupe_window_days: int = Field(ge=0)
    recipient_dedupe_window_days: int = Field(ge=0)
    require_manual_review_before_send: bool | None = True


class PolicyLimits(StrictModel):
    daily_send_limit: int = Field(ge=0)
    weekly_send_limit: int = Field(ge=0)


class PolicyReviewThresholds(StrictModel):
    minimum_required_confidence: float = Field(ge=0, le=1)
    block_needs_review_required_fields: bool


class Policy(StrictModel):
    schema_version: Literal["1.0"]
    policy_id: str = Field(min_length=1)
    created_at: datetime
    exclusions: PolicyExclusions
    outreach: PolicyOutreach
    limits: PolicyLimits
    review_thresholds: PolicyReviewThresholds
    forbidden_claims: list[str] | None = None


class SendIntentAttachmentRef(StrictModel):
    attachment_id: str = Field(min_length=1)
    path: str = Field(min_length=1)
    kind: Literal["cv", "cover_letter", "portfolio", "other"]
    exists_at_draft_time: bool


class SendIntent(StrictModel):
    schema_version: Literal["1.0"]
    intent_id: str = Field(min_length=1)
    run_id: str = Field(min_length=1)
    company_id: str = Field(min_length=1)
    contact_id: str = Field(min_length=1)
    email_draft_id: str = Field(min_length=1)
    recipient_email: EmailStr
    recipient_name: str | None = None
    company_domain: str | None = None
    subject: str = Field(min_length=1)
    body_text: str = Field(min_length=1)
    body_html: str | None = None
    attachments: list[SendIntentAttachmentRef]
    source_refs: list[str] = Field(min_length=1)
    claim_refs: list[str] | None = None
    policy_id: str = Field(min_length=1)
    profile_id: str = Field(min_length=1)
    master_cv_profile_id: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    review_flags: list[str]
    created_by: Literal["codex_agent"]


class ProvenancedText(StrictModel):
    value: str = Field(min_length=1)
    provenance: Provenance


class UserIdentity(StrictModel):
    display_name: str = Field(min_length=1)
    headline: str | None = None
    location: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    links: list[AnyUrl] | None = None


class UserLanguage(StrictModel):
    language: str = Field(min_length=1)
    level: str
    provenance: Provenance


class UserPreferences(StrictModel):
    target_roles: list[ProvenancedText]
    target_locations: list[ProvenancedText]
    remote_preferences: list[str]
    relocation_preferences: list[ProvenancedText] | None = None
    communication_tone: ProvenancedText
    availability: ProvenancedText | None = None


class ReviewItem(StrictModel):
    field: str
    reason: str


class ProvenanceSummary(StrictModel):
    source_documents: list[str]
    interview_notes: list[str]


class UserProfile(StrictModel):
    schema_version: Literal["1.0"]
    profile_id: str = Field(min_length=1)
    created_at: datetime
    updated_at: datetime | None = None
    identity: UserIdentity
    work_authorization: list[ProvenancedText] | None = None
    languages: list[UserLanguage] | None = None
    preferences: UserPreferences
    review_items: list[ReviewItem] | None = None
    provenance_summary: ProvenanceSummary


AGENT_OUTPUT_MODELS = {
    "company_candidate.schema.json": CompanyCandidate,
    "contact_candidate.schema.json": ContactCandidate,
    "email_draft.schema.json": EmailDraft,
    "fit_evaluation.schema.json": FitEvaluation,
    "gate_result.schema.json": GateResult,
    "master_cv_profile.schema.json": MasterCvProfile,
    "policy.schema.json": Policy,
    "send_intent.schema.json": SendIntent,
    "user_profile.schema.json": UserProfile,
}
