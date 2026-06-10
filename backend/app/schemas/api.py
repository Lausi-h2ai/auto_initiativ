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


class OnboardingArtifactContentResponse(BaseModel):
    run_id: str
    filename: str
    path: str
    exists: bool
    raw_text: str | None = None
    json_content: dict[str, Any] | list[Any] | None = None


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


class CompanyResearchCampaignRequest(BaseModel):
    run_id: str | None = Field(default=None, min_length=1, max_length=120)
    role_focus: str = Field(default="Profile-aligned roles", min_length=1, max_length=240)
    locations: list[str] = Field(default_factory=list)
    time_budget_minutes: int = Field(default=30, ge=1, le=240)
    max_companies: int = Field(default=30, ge=1, le=100)
    notes: str | None = Field(default=None, max_length=2000)


class CompanyResearchCampaignResponse(BaseModel):
    run_id: str
    status: str
    run_path: str
    input_path: str
    output_path: str
    prompt_path: str
    import_endpoint: str
    expected_output_files: list[str]
    next_action: str


class CompanyResearchLaunchResponse(BaseModel):
    run_id: str
    status: str
    runtime: str
    command: list[str]
    workdir: str
    status_endpoint: str


class CompanyResearchStatusResponse(BaseModel):
    run_id: str
    runtime: str
    status: str
    state: dict[str, Any]
    artifact_counts: dict[str, int]
    validation: dict[str, Any]
    import_state: dict[str, Any]
    logs: list[dict[str, Any]]


class CompanyResearchImportResponse(BaseModel):
    run_id: str
    import_result: ImportResponse
    status: CompanyResearchStatusResponse


class ApplicationDraftRequest(BaseModel):
    run_id: str | None = Field(default=None, min_length=1, max_length=120)
    company_id: str = Field(min_length=1, max_length=240)
    contact_id: str | None = Field(default=None, min_length=1, max_length=240)
    language: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)


class ApplicationDraftResponse(BaseModel):
    run_id: str
    status: str
    company_id: str
    contact_id: str
    draft_id: str
    run_path: str
    input_path: str
    output_path: str
    prompt_path: str
    launch_endpoint: str
    import_endpoint: str
    status_endpoint: str
    expected_output_files: list[str]
    expected_attachment_files: list[str]
    next_action: str


class ApplicationDraftLaunchResponse(BaseModel):
    run_id: str
    status: str
    runtime: str
    command: list[str]
    workdir: str
    status_endpoint: str


class ApplicationDraftStatusResponse(BaseModel):
    run_id: str
    runtime: str
    status: str
    state: dict[str, Any]
    artifact_counts: dict[str, int]
    validation: dict[str, Any]
    import_state: dict[str, Any]
    logs: list[dict[str, Any]]


class ApplicationDraftImportResponse(BaseModel):
    run_id: str
    import_result: ImportResponse
    status: ApplicationDraftStatusResponse


class ApplicationDraftBatchRequest(BaseModel):
    mode: str = Field(default="selected", pattern="^(selected|all_missing)$")
    company_ids: list[str] = Field(default_factory=list)
    concurrency: int = Field(default=1, ge=1, le=3)
    language: str | None = Field(default=None, max_length=40)
    notes: str | None = Field(default=None, max_length=2000)


class ApplicationDraftBatchItemResponse(BaseModel):
    company_id: str
    status: str
    reason: str | None = None
    run_id: str | None = None
    draft_id: str | None = None
    contact_id: str | None = None
    detail: str | None = None


class ApplicationDraftBatchResponse(BaseModel):
    batch_id: str
    status: str
    mode: str
    concurrency: int
    requested_count: int
    queued_count: int
    launched_count: int
    completed_count: int
    skipped_count: int
    failed_count: int
    status_endpoint: str
    items: list[ApplicationDraftBatchItemResponse]


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
    send_approval_snapshots: int = 0
    sent_messages: int = 0
    send_intents_by_status: dict[str, int]
    gate_results_by_status: dict[str, int]
    outreach_records_by_status: dict[str, int]


class EmailDeliverySettingsResponse(BaseModel):
    sending_enabled: bool
    provider: str
    allow_real_recipients: bool
    sandbox_recipient: str | None = None
    gmail_configured: bool
    mode: str


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
    is_active_profile_scope: bool = False
    can_draft_application: bool = False
    application_draft_block_reason: str | None = None
    has_application_draft: bool = False
    has_send_intent: bool = False
    send_intent_status: str | None = None
    send_gate_status: str | None = None
    has_been_contacted: bool = False
    outreach_status: str | None = None
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
    queued_send_intent_id: str | None = None
    queued_gate_status: str | None = None


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


class QueueDraftForSendRequest(BaseModel):
    reviewer_id: str = Field(min_length=1, max_length=120)


class QueueDraftForSendResponse(BaseModel):
    send_intent: SendIntentResponse
    gate_result: GateResultSummaryResponse
    created: bool


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


class SendBatchRequest(BaseModel):
    intent_ids: list[str] = Field(min_length=1, max_length=100)
    reviewer_id: str = Field(min_length=1, max_length=120)


class SendBatchItemResponse(BaseModel):
    intent_id: str
    status: str
    approval_id: str | None = None
    gate_result_id: str | None = None
    reservation_id: str | None = None
    sent_message_id: str | None = None
    outreach_record_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    detail: str | None = None


class SendBatchResponse(BaseModel):
    batch_id: str
    status: str
    requested_count: int
    sent_count: int
    blocked_count: int
    items: list[SendBatchItemResponse]


class SentMessageResponse(BaseModel):
    id: int
    sent_message_id: str
    approval_id: str | None = None
    send_intent_id: int | None = None
    external_intent_id: str | None = None
    external_company_id: str | None = None
    external_contact_id: str | None = None
    external_email_draft_id: str | None = None
    provider: str
    provider_message_id: str | None = None
    provider_thread_id: str | None = None
    provider_url: str | None = None
    status: str
    normalized_recipient_email: str
    company_policy_key: str
    network_performed: bool
    subject: str | None = None
    body_text: str | None = None
    body_html: str | None = None
    attachments: list[Any]
    provider_response: dict[str, Any]
    error: dict[str, Any]
    created_at: datetime
    accepted_at: datetime | None = None


class OutboxAttachmentLink(BaseModel):
    attachment_id: str
    label: str
    url: str
    kind: str | None = None


class OutboxDraftResponse(BaseModel):
    draft_id: str
    intent_id: str | None = None
    company_id: str
    company_name: str
    email_address: str | None = None
    drafted_at: datetime
    status: str
    status_label: str
    blocker_code: str | None = None
    subject: str
    body_text: str
    email_url: str
    cv: OutboxAttachmentLink | None = None


class OutboxSentResponse(BaseModel):
    sent_message_id: str
    company_id: str | None = None
    company_name: str
    email_address: str
    sent_at: datetime
    status: str
    subject: str | None = None
    body_text: str | None = None
    email_url: str
    cv: OutboxAttachmentLink | None = None
    provider_url: str | None = None


class OutboxSendAllRequest(BaseModel):
    reviewer_id: str = Field(default="local-user", min_length=1, max_length=120)


class OutboxSendAllResponse(BaseModel):
    requested_count: int
    sent_count: int
    blocked_count: int
    batch: SendBatchResponse | None = None
    drafts: list[OutboxDraftResponse]


class OutreachResolutionRequest(BaseModel):
    resolution: str = Field(pattern="^(mark_sent|mark_not_sent|keep_blocked|void_record)$")
    reviewer_id: str = Field(min_length=1, max_length=120)
    comment: str = Field(min_length=1, max_length=2000)


class OutreachResolutionResponse(BaseModel):
    outreach_record: OutreachRecordResponse
    previous_status: str
    resolution: str
