from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str
    dry_run: bool


class ImportedFileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    path: str
    filename: str
    schema_name: str | None
    sha256: str | None
    size_bytes: int
    status: str
    imported_at: datetime


class ValidationResultResponse(BaseModel):
    id: int
    run_id: str
    imported_file_id: int | None
    filename: str
    status: str
    schema_name: str | None
    error_count: int
    errors: list[dict[str, Any]]
    reason_codes: list[str]
    validated_at: datetime


class RunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: str
    agent_type: str | None
    output_path: str
    status: str
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class RunDetailResponse(RunResponse):
    files: list[ImportedFileResponse]


class ImportSummaryItem(BaseModel):
    filename: str
    status: str
    schema_name: str | None
    error_count: int
    reason_codes: list[str]


class ImportResponse(BaseModel):
    run: RunResponse
    results: list[ImportSummaryItem]


class OnboardingChatMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=12000)


class OnboardingChatEntryResponse(BaseModel):
    run_id: str
    role: str
    content: str
    created_at: str
    raw_capture: str | None = None
    event: str | None = None


class OnboardingSessionStateResponse(BaseModel):
    run_id: str
    status: str
    updated_at: str
    tmux: dict[str, Any] | None = None
    last_error: str | None = None
    entries: list[OnboardingChatEntryResponse] = Field(default_factory=list)


class OnboardingChatStartResponse(BaseModel):
    run_id: str
    status: str
    trust_prompt_accepted: bool
    session_state: OnboardingSessionStateResponse | None = None
    entries: list[OnboardingChatEntryResponse]


class OnboardingChatMessageResponse(BaseModel):
    run_id: str
    reply: str
    transcript_path: str
    session_state: OnboardingSessionStateResponse | None = None
    entries: list[OnboardingChatEntryResponse]


class OnboardingArtifactResponse(BaseModel):
    filename: str
    schema_name: str | None = None
    exists: bool
    status: str
    review_state: str
    path: str
    error_count: int = 0
    reason_codes: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    snapshot_type: str | None = None
    snapshot_id: int | None = None
    snapshot_external_id: str | None = None
    snapshot_status: str | None = None


class OnboardingArtifactsResponse(BaseModel):
    run_id: str
    output_path: str
    artifacts: list[OnboardingArtifactResponse]


class OnboardingInputFileResponse(BaseModel):
    filename: str
    path: str
    size_bytes: int


class OnboardingInputFilesResponse(BaseModel):
    run_id: str
    input_path: str
    files: list[OnboardingInputFileResponse]


class OnboardingArtifactImportResponse(BaseModel):
    run_id: str
    import_result: ImportResponse
    artifacts: list[OnboardingArtifactResponse]


class OnboardingChatFinishResponse(BaseModel):
    run_id: str
    reply: str
    transcript_path: str
    import_result: ImportResponse
    artifacts: list[OnboardingArtifactResponse] = Field(default_factory=list)
    entries: list[OnboardingChatEntryResponse]


class OnboardingChatActionResponse(BaseModel):
    run_id: str
    status: str
    session_state: OnboardingSessionStateResponse
    entries: list[OnboardingChatEntryResponse]


class OnboardingTerminalLaunchResponse(BaseModel):
    run_id: str
    status: str
    command: str
    session_state: OnboardingSessionStateResponse


class OnboardingPromotionRequest(BaseModel):
    reviewer_id: str
    confirm_user_profile: bool
    confirm_master_cv_profile: bool
    confirm_policy: bool


class OnboardingPromotionIssueResponse(BaseModel):
    code: str
    message: str
    snapshot_type: str | None = None
    field: str | None = None


class OnboardingSnapshotResponse(BaseModel):
    snapshot_type: str
    id: int
    external_id: str
    status: str


class ProfileSnapshotSummaryResponse(BaseModel):
    snapshot_type: str
    id: int
    external_id: str
    status: str
    created_at: datetime


class ProfileSummaryResponse(BaseModel):
    has_approved_profile: bool
    approved_user_profile: ProfileSnapshotSummaryResponse | None = None
    candidate_user_profiles: list[ProfileSnapshotSummaryResponse] = Field(default_factory=list)
    approved_master_cv_profile: ProfileSnapshotSummaryResponse | None = None
    approved_policy: ProfileSnapshotSummaryResponse | None = None


class OnboardingPromotionResponse(BaseModel):
    run_id: str
    status: str
    promoted: list[OnboardingSnapshotResponse]
    issues: list[OnboardingPromotionIssueResponse]


class AuditLogResponse(BaseModel):
    id: int
    run_id: str | None
    actor_type: str
    action: str
    entity_type: str
    entity_id: str | None
    result_status: str
    reason_codes: list[str]
    metadata: dict[str, Any]
    created_at: datetime


class GateEvaluationResponse(BaseModel):
    gate_result_id: str
    intent_id: str
    status: str
    checks: list[dict[str, str]]
    reasons: list[dict[str, str]]
    evaluated_at: datetime
    policy_snapshot_id: str | None


class DashboardSummaryResponse(BaseModel):
    runs: int
    companies: int
    contacts: int
    fit_evaluations: int
    email_drafts: int
    send_intents: int
    gate_results: int
    outreach_records: int
    send_intents_by_status: dict[str, int]
    gate_results_by_status: dict[str, int]
    outreach_records_by_status: dict[str, int]


class GateResultSummaryResponse(BaseModel):
    gate_result_id: str
    status: str
    evaluated_at: datetime
    reasons: list[Any]


class CompanyResponse(BaseModel):
    id: int
    company_id: str
    name: str
    raw_domain: str | None
    normalized_domain: str | None
    normalized_name: str
    company_policy_key: str
    company_policy_key_kind: str
    description: str | None
    industry_tags: list[Any]
    locations: list[Any]
    remote_policy: str | None
    source_refs: list[Any]
    confidence: float
    review_flags: list[Any]
    policy_conflicts: list[Any]
    raw: dict[str, Any]
    imported_file_id: int | None
    created_at: datetime
    updated_at: datetime


class ContactResponse(BaseModel):
    id: int
    contact_id: str
    company_id: int | None
    external_company_id: str
    name: str | None
    role_title: str | None
    raw_email: str
    normalized_recipient_email: str
    email_source: str
    profile_url: str | None
    source_refs: list[Any]
    confidence: float
    review_flags: list[Any]
    raw: dict[str, Any]
    imported_file_id: int | None
    created_at: datetime
    updated_at: datetime


class FitEvaluationResponse(BaseModel):
    id: int
    evaluation_id: str
    company_id: int | None
    external_company_id: str
    user_profile_snapshot_id: int | None
    policy_snapshot_id: int | None
    fit_score: float
    decision: str
    reasons: list[Any]
    risks: list[Any]
    source_refs: list[Any]
    confidence: float
    review_flags: list[Any]
    raw: dict[str, Any]
    imported_file_id: int | None
    created_at: datetime


class EmailDraftResponse(BaseModel):
    id: int
    draft_id: str
    company_id: int | None
    external_company_id: str
    contact_id: int | None
    external_contact_id: str
    subject: str
    body_text: str
    body_html: str | None
    tone: str | None
    claim_refs: list[Any]
    source_refs: list[Any]
    attachments: list[Any]
    confidence: float
    review_flags: list[Any]
    raw: dict[str, Any]
    imported_file_id: int | None
    created_at: datetime


class SendIntentResponse(BaseModel):
    id: int
    intent_id: str
    run_id: str
    company_id: int | None
    external_company_id: str
    contact_id: int | None
    external_contact_id: str
    email_draft_id: int | None
    external_email_draft_id: str
    raw_recipient_email: str
    normalized_recipient_email: str
    recipient_name: str | None
    company_domain: str | None
    subject: str
    body_text: str
    body_html: str | None
    attachments: list[Any]
    source_refs: list[Any]
    claim_refs: list[Any]
    policy_snapshot_id: int | None
    external_policy_id: str
    user_profile_snapshot_id: int | None
    external_profile_id: str
    master_cv_profile_snapshot_id: int | None
    external_master_cv_profile_id: str
    confidence: float
    review_flags: list[Any]
    created_by: str
    status: str
    raw: dict[str, Any]
    imported_file_id: int | None
    created_at: datetime
    updated_at: datetime
    latest_gate_result: GateResultSummaryResponse | None = None


class GateResultResponse(BaseModel):
    id: int
    gate_result_id: str
    send_intent_id: int | None
    external_intent_id: str
    status: str
    checks: list[Any]
    reasons: list[Any]
    external_reservation_id: str | None
    evaluated_at: datetime
    policy_snapshot_id: int | None
    external_policy_id: str | None
    raw: dict[str, Any]
    imported_file_id: int | None
    imported_at: datetime


class OutreachRecordResponse(BaseModel):
    id: int
    outreach_record_id: str
    send_intent_id: int | None
    company_id: int | None
    contact_id: int | None
    normalized_recipient_email: str
    company_policy_key: str
    policy_snapshot_id: int | None
    channel: str
    status: str
    dedupe_recipient: bool
    dedupe_company: bool
    occurred_at: datetime
    source: str
    notes: dict[str, Any]
