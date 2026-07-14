from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Float, Index, Text, UniqueConstraint, text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class WorkspaceOwned(SQLModel):
    """Marker used by the session layer to enforce workspace isolation."""

    workspace_id: Optional[int] = Field(default=None, foreign_key="workspaces.id", index=True)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: Optional[int] = Field(default=None, primary_key=True)
    google_subject: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    display_name: str
    avatar_url: Optional[str] = None
    role: str = Field(default="user", index=True)
    status: str = Field(default="active", index=True)
    last_login_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Workspace(SQLModel, table=True):
    __tablename__ = "workspaces"

    id: Optional[int] = Field(default=None, primary_key=True)
    workspace_id: str = Field(index=True, unique=True)
    owner_user_id: int = Field(foreign_key="users.id", index=True, unique=True)
    name: str
    status: str = Field(default="active", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Invitation(SQLModel, table=True):
    __tablename__ = "invitations"

    id: Optional[int] = Field(default=None, primary_key=True)
    invitation_id: str = Field(index=True, unique=True)
    email: str = Field(index=True, unique=True)
    invited_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    role: str = Field(default="user", index=True)
    status: str = Field(default="pending", index=True)
    accepted_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    accepted_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)


class AuthSession(SQLModel, table=True):
    __tablename__ = "auth_sessions"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True, unique=True)
    token_hash: str = Field(index=True, unique=True)
    user_id: int = Field(foreign_key="users.id", index=True)
    expires_at: datetime = Field(index=True)
    last_seen_at: datetime = Field(default_factory=utc_now)
    revoked_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)


class OAuthState(SQLModel, table=True):
    __tablename__ = "oauth_states"

    id: Optional[int] = Field(default=None, primary_key=True)
    state_hash: str = Field(index=True, unique=True)
    purpose: str = Field(index=True)
    user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    code_verifier: str
    redirect_uri: str
    expires_at: datetime = Field(index=True)
    consumed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)


class GmailConnection(SQLModel, table=True):
    __tablename__ = "gmail_connections"

    id: Optional[int] = Field(default=None, primary_key=True)
    connection_id: str = Field(index=True, unique=True)
    user_id: int = Field(foreign_key="users.id", index=True, unique=True)
    google_subject: str = Field(index=True)
    email: str = Field(index=True)
    encrypted_credentials: str = Field(sa_column=Column(Text))
    scopes_json: str = Field(default="[]", sa_column=Column(Text))
    status: str = Field(default="connected", index=True)
    connected_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    revoked_at: Optional[datetime] = None


class AdminAccessAudit(SQLModel, table=True):
    __tablename__ = "admin_access_audits"

    id: Optional[int] = Field(default=None, primary_key=True)
    access_id: str = Field(index=True, unique=True)
    admin_user_id: int = Field(foreign_key="users.id", index=True)
    target_workspace_id: int = Field(foreign_key="workspaces.id", index=True)
    action: str = Field(index=True)
    resource_type: Optional[str] = Field(default=None, index=True)
    resource_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now)


class Campaign(WorkspaceOwned, table=True):
    __tablename__ = "campaigns"
    __table_args__ = (UniqueConstraint("workspace_id", "campaign_id", name="uq_campaigns_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: str = Field(index=True)
    name: str
    campaign_type: str = Field(default="initiative_outreach", index=True)
    status: str = Field(default="draft", index=True)
    sending_mode: str = Field(default="prepare_only", index=True)
    brief_json: str = Field(default="{}", sa_column=Column(Text))
    user_profile_snapshot_id: Optional[int] = Field(default=None, foreign_key="user_profile_snapshots.id", index=True)
    master_cv_profile_snapshot_id: Optional[int] = Field(default=None, foreign_key="master_cv_profile_snapshots.id", index=True)
    policy_snapshot_id: Optional[int] = Field(default=None, foreign_key="policy_snapshots.id", index=True)
    started_at: Optional[datetime] = None
    paused_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class OnboardingSession(WorkspaceOwned, table=True):
    __tablename__ = "onboarding_sessions"
    __table_args__ = (UniqueConstraint("workspace_id", "session_id", name="uq_onboarding_sessions_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: str = Field(index=True)
    run_id: str = Field(index=True)
    status: str = Field(default="not_started", index=True)
    transport: str = Field(default="pi_rpc", index=True)
    transport_metadata_json: str = Field(default="{}", sa_column=Column(Text))
    transcript_json: str = Field(default="[]", sa_column=Column(Text))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CampaignCompany(WorkspaceOwned, table=True):
    __tablename__ = "campaign_companies"
    __table_args__ = (UniqueConstraint("campaign_id", "company_id", name="uq_campaign_companies_campaign_company"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaigns.id", index=True)
    company_id: int = Field(foreign_key="companies.id", index=True)
    stage: str = Field(default="discovered", index=True)
    disposition: Optional[str] = Field(default=None, index=True)
    stage_reason: Optional[str] = Field(default=None, sa_column=Column(Text))
    entered_stage_at: datetime = Field(default_factory=utc_now)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class JobPosting(WorkspaceOwned, table=True):
    __tablename__ = "job_postings"
    __table_args__ = (UniqueConstraint("workspace_id", "job_id", name="uq_job_postings_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    job_id: str = Field(index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    external_company_id: str = Field(index=True)
    title: str = Field(index=True)
    source_url: str = Field(sa_column=Column(Text))
    canonical_url: str = Field(sa_column=Column(Text))
    application_url: str = Field(sa_column=Column(Text))
    employer_website_url: Optional[str] = Field(default=None, sa_column=Column(Text))
    source_domain: str = Field(index=True)
    source_kind: str = Field(index=True)
    external_listing_id: Optional[str] = Field(default=None, index=True)
    fingerprint: str = Field(index=True)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    locations_json: str = Field(default="[]", sa_column=Column(Text))
    remote_policy: Optional[str] = None
    employment_types_json: str = Field(default="[]", sa_column=Column(Text))
    compensation_json: str = Field(default="{}", sa_column=Column(Text))
    languages_json: str = Field(default="[]", sa_column=Column(Text))
    requirements_json: str = Field(default="[]", sa_column=Column(Text))
    responsibilities_json: str = Field(default="[]", sa_column=Column(Text))
    date_posted: Optional[datetime] = Field(default=None, index=True)
    valid_through: Optional[datetime] = Field(default=None, index=True)
    vacancy_status: str = Field(default="needs_verification", index=True)
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    last_verified_at: Optional[datetime] = Field(default=None, index=True)
    verification_evidence_json: str = Field(default="{}", sa_column=Column(Text))
    source_refs_json: str = Field(default="[]", sa_column=Column(Text))
    confidence: float = Field(default=0.0, sa_column=Column(Float))
    review_flags_json: str = Field(default="[]", sa_column=Column(Text))
    raw_json: str = Field(default="{}", sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CampaignJob(WorkspaceOwned, table=True):
    __tablename__ = "campaign_jobs"
    __table_args__ = (UniqueConstraint("campaign_id", "job_posting_id", name="uq_campaign_jobs_campaign_job"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    campaign_id: int = Field(foreign_key="campaigns.id", index=True)
    job_posting_id: int = Field(foreign_key="job_postings.id", index=True)
    application_status: str = Field(default="discovered", index=True)
    status_note: Optional[str] = Field(default=None, sa_column=Column(Text))
    applied_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class JobFitEvaluation(WorkspaceOwned, table=True):
    __tablename__ = "job_fit_evaluations"
    __table_args__ = (UniqueConstraint("workspace_id", "evaluation_id", name="uq_job_fit_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    evaluation_id: str = Field(index=True)
    job_posting_id: Optional[int] = Field(default=None, foreign_key="job_postings.id", index=True)
    external_job_id: str = Field(index=True)
    company_fit_score: float = Field(sa_column=Column(Float))
    role_fit_score: float = Field(sa_column=Column(Float))
    decision: str = Field(index=True)
    reasons_json: str = Field(default="[]", sa_column=Column(Text))
    gaps_json: str = Field(default="[]", sa_column=Column(Text))
    source_refs_json: str = Field(default="[]", sa_column=Column(Text))
    confidence: float = Field(sa_column=Column(Float))
    review_flags_json: str = Field(default="[]", sa_column=Column(Text))
    raw_json: str = Field(default="{}", sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    created_at: datetime = Field(default_factory=utc_now)


class JobApplicationPackage(WorkspaceOwned, table=True):
    __tablename__ = "job_application_packages"
    __table_args__ = (UniqueConstraint("workspace_id", "package_id", name="uq_job_packages_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    package_id: str = Field(index=True)
    campaign_job_id: int = Field(foreign_key="campaign_jobs.id", index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(default="ready", index=True)
    cv_document_id: Optional[int] = Field(default=None, foreign_key="documents.id")
    cover_letter_text: str = Field(sa_column=Column(Text))
    answer_kit_json: str = Field(default="[]", sa_column=Column(Text))
    claim_refs_json: str = Field(default="[]", sa_column=Column(Text))
    review_flags_json: str = Field(default="[]", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class JobSourceTrust(WorkspaceOwned, table=True):
    __tablename__ = "job_source_trust"
    __table_args__ = (UniqueConstraint("workspace_id", "domain", name="uq_job_source_trust_workspace_domain"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    domain: str = Field(index=True)
    trust_level: str = Field(default="discovery_only", index=True)
    is_builtin: bool = Field(default=False)
    enabled: bool = Field(default=True)
    notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class AgentTask(WorkspaceOwned, table=True):
    __tablename__ = "agent_tasks"
    __table_args__ = (UniqueConstraint("workspace_id", "task_id", name="uq_agent_tasks_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    task_id: str = Field(index=True)
    campaign_id: Optional[int] = Field(default=None, foreign_key="campaigns.id", index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    agent_role: str = Field(index=True)
    task_type: str = Field(index=True)
    status: str = Field(default="queued", index=True)
    progress: int = Field(default=0)
    narrative: str = Field(default="Queued for specialist review.", sa_column=Column(Text))
    input_json: str = Field(default="{}", sa_column=Column(Text))
    output_json: str = Field(default="{}", sa_column=Column(Text))
    attempt_count: int = Field(default=0)
    max_attempts: int = Field(default=3)
    available_at: datetime = Field(default_factory=utc_now, index=True)
    locked_at: Optional[datetime] = None
    locked_by: Optional[str] = Field(default=None, index=True)
    last_error: Optional[str] = Field(default=None, sa_column=Column(Text))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ReviewException(WorkspaceOwned, table=True):
    __tablename__ = "review_exceptions"
    __table_args__ = (UniqueConstraint("workspace_id", "exception_id", name="uq_review_exceptions_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    exception_id: str = Field(index=True)
    campaign_id: Optional[int] = Field(default=None, foreign_key="campaigns.id", index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    agent_task_id: Optional[int] = Field(default=None, foreign_key="agent_tasks.id", index=True)
    category: str = Field(index=True)
    title: str
    explanation: str = Field(sa_column=Column(Text))
    recommended_action: str = Field(sa_column=Column(Text))
    status: str = Field(default="open", index=True)
    resolution: Optional[str] = Field(default=None, sa_column=Column(Text))
    resolved_by_user_id: Optional[int] = Field(default=None, foreign_key="users.id", index=True)
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Document(WorkspaceOwned, table=True):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("workspace_id", "document_id", name="uq_documents_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    document_id: str = Field(index=True)
    campaign_id: Optional[int] = Field(default=None, foreign_key="campaigns.id", index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    run_id: Optional[str] = Field(default=None, index=True)
    document_type: str = Field(index=True)
    title: str
    filename: str
    relative_path: str
    mime_type: str
    size_bytes: int = 0
    content_hash: Optional[str] = Field(default=None, index=True)
    provenance_json: str = Field(default="{}", sa_column=Column(Text))
    status: str = Field(default="ready", index=True)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Run(WorkspaceOwned, table=True):
    __tablename__ = "runs"
    __table_args__ = (UniqueConstraint("workspace_id", "run_id", name="uq_runs_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    agent_type: Optional[str] = None
    output_path: str
    status: str = Field(index=True)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ImportedFile(WorkspaceOwned, table=True):
    __tablename__ = "imported_files"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    path: str
    filename: str = Field(index=True)
    schema_name: Optional[str] = Field(default=None, index=True)
    sha256: Optional[str] = None
    size_bytes: int = 0
    status: str = Field(index=True)
    raw_json: Optional[str] = Field(default=None, sa_column=Column(Text))
    imported_at: datetime = Field(default_factory=utc_now)


class ValidationResult(WorkspaceOwned, table=True):
    __tablename__ = "validation_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True)
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    filename: str = Field(index=True)
    status: str = Field(index=True)
    schema_name: Optional[str] = Field(default=None, index=True)
    error_count: int
    errors_json: str = Field(default="[]", sa_column=Column(Text))
    reason_codes_json: str = Field(default="[]", sa_column=Column(Text))
    validated_at: datetime = Field(default_factory=utc_now)


class AuditLog(WorkspaceOwned, table=True):
    __tablename__ = "audit_logs"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: Optional[str] = Field(default=None, index=True)
    actor_type: str = Field(index=True)
    action: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: Optional[str] = Field(default=None, index=True)
    result_status: str = Field(index=True)
    reason_codes_json: str = Field(default="[]", sa_column=Column(Text))
    metadata_json: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)


class UserProfileSnapshot(WorkspaceOwned, table=True):
    __tablename__ = "user_profile_snapshots"
    __table_args__ = (UniqueConstraint("workspace_id", "profile_id", name="uq_user_profiles_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: str = Field(index=True)
    schema_version: str
    source_created_at: Optional[datetime] = None
    source_updated_at: Optional[datetime] = None
    content_hash: str = Field(index=True)
    status: str = Field(default="imported", index=True)
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    imported_at: datetime = Field(default_factory=utc_now)


class MasterCvProfileSnapshot(WorkspaceOwned, table=True):
    __tablename__ = "master_cv_profile_snapshots"
    __table_args__ = (UniqueConstraint("workspace_id", "profile_id", name="uq_master_cv_profiles_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: str = Field(index=True)
    schema_version: str
    source_created_at: Optional[datetime] = None
    content_hash: str = Field(index=True)
    status: str = Field(default="imported", index=True)
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    imported_at: datetime = Field(default_factory=utc_now)


class PolicySnapshot(WorkspaceOwned, table=True):
    __tablename__ = "policy_snapshots"
    __table_args__ = (UniqueConstraint("workspace_id", "policy_id", name="uq_policies_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    policy_id: str = Field(index=True)
    schema_version: str
    source_created_at: Optional[datetime] = None
    content_hash: str = Field(index=True)
    status: str = Field(default="imported", index=True)
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    imported_at: datetime = Field(default_factory=utc_now)


class Company(WorkspaceOwned, table=True):
    __tablename__ = "companies"
    __table_args__ = (UniqueConstraint("workspace_id", "company_id", name="uq_companies_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: str = Field(index=True)
    name: str = Field(index=True)
    raw_domain: Optional[str] = None
    normalized_domain: Optional[str] = Field(default=None, index=True)
    normalized_name: str = Field(index=True)
    company_policy_key: str = Field(index=True)
    company_policy_key_kind: str = Field(index=True)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    industry_tags_json: str = Field(default="[]", sa_column=Column(Text))
    locations_json: str = Field(default="[]", sa_column=Column(Text))
    remote_policy: Optional[str] = None
    source_refs_json: str = Field(default="[]", sa_column=Column(Text))
    confidence: float = Field(sa_column=Column(Float))
    review_flags_json: str = Field(default="[]", sa_column=Column(Text))
    policy_conflicts_json: str = Field(default="[]", sa_column=Column(Text))
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class Contact(WorkspaceOwned, table=True):
    __tablename__ = "contacts"
    __table_args__ = (UniqueConstraint("workspace_id", "contact_id", name="uq_contacts_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    contact_id: str = Field(index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    external_company_id: str = Field(index=True)
    name: Optional[str] = None
    role_title: Optional[str] = None
    raw_email: str
    normalized_recipient_email: str = Field(index=True)
    email_source: str = Field(index=True)
    profile_url: Optional[str] = None
    source_refs_json: str = Field(default="[]", sa_column=Column(Text))
    confidence: float = Field(sa_column=Column(Float))
    review_flags_json: str = Field(default="[]", sa_column=Column(Text))
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class FitEvaluation(WorkspaceOwned, table=True):
    __tablename__ = "fit_evaluations"
    __table_args__ = (UniqueConstraint("workspace_id", "evaluation_id", name="uq_fit_evaluations_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    evaluation_id: str = Field(index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    external_company_id: str = Field(index=True)
    user_profile_snapshot_id: Optional[int] = Field(default=None, foreign_key="user_profile_snapshots.id", index=True)
    policy_snapshot_id: Optional[int] = Field(default=None, foreign_key="policy_snapshots.id", index=True)
    fit_score: float = Field(sa_column=Column(Float))
    decision: str = Field(index=True)
    reasons_json: str = Field(default="[]", sa_column=Column(Text))
    risks_json: str = Field(default="[]", sa_column=Column(Text))
    source_refs_json: str = Field(default="[]", sa_column=Column(Text))
    confidence: float = Field(sa_column=Column(Float))
    review_flags_json: str = Field(default="[]", sa_column=Column(Text))
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    created_at: datetime = Field(default_factory=utc_now)


class EmailDraft(WorkspaceOwned, table=True):
    __tablename__ = "email_drafts"
    __table_args__ = (UniqueConstraint("workspace_id", "draft_id", name="uq_email_drafts_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    draft_id: str = Field(index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    external_company_id: str = Field(index=True)
    contact_id: Optional[int] = Field(default=None, foreign_key="contacts.id", index=True)
    external_contact_id: str = Field(index=True)
    subject: str
    body_text: str = Field(sa_column=Column(Text))
    body_html: Optional[str] = Field(default=None, sa_column=Column(Text))
    tone: Optional[str] = None
    claim_refs_json: str = Field(default="[]", sa_column=Column(Text))
    source_refs_json: str = Field(default="[]", sa_column=Column(Text))
    attachments_json: str = Field(default="[]", sa_column=Column(Text))
    confidence: float = Field(sa_column=Column(Float))
    review_flags_json: str = Field(default="[]", sa_column=Column(Text))
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    created_at: datetime = Field(default_factory=utc_now)


class SendIntent(WorkspaceOwned, table=True):
    __tablename__ = "send_intents"
    __table_args__ = (UniqueConstraint("workspace_id", "intent_id", name="uq_send_intents_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    intent_id: str = Field(index=True)
    run_id: str = Field(index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    external_company_id: str = Field(index=True)
    contact_id: Optional[int] = Field(default=None, foreign_key="contacts.id", index=True)
    external_contact_id: str = Field(index=True)
    email_draft_id: Optional[int] = Field(default=None, foreign_key="email_drafts.id", index=True)
    external_email_draft_id: str = Field(index=True)
    raw_recipient_email: str
    normalized_recipient_email: str = Field(index=True)
    recipient_name: Optional[str] = None
    company_domain: Optional[str] = None
    subject: str
    body_text: str = Field(sa_column=Column(Text))
    body_html: Optional[str] = Field(default=None, sa_column=Column(Text))
    attachments_json: str = Field(default="[]", sa_column=Column(Text))
    source_refs_json: str = Field(default="[]", sa_column=Column(Text))
    claim_refs_json: str = Field(default="[]", sa_column=Column(Text))
    policy_snapshot_id: Optional[int] = Field(default=None, foreign_key="policy_snapshots.id", index=True)
    external_policy_id: str = Field(index=True)
    user_profile_snapshot_id: Optional[int] = Field(default=None, foreign_key="user_profile_snapshots.id", index=True)
    external_profile_id: str = Field(index=True)
    master_cv_profile_snapshot_id: Optional[int] = Field(default=None, foreign_key="master_cv_profile_snapshots.id", index=True)
    external_master_cv_profile_id: str = Field(index=True)
    confidence: float = Field(sa_column=Column(Float))
    review_flags_json: str = Field(default="[]", sa_column=Column(Text))
    created_by: str
    status: str = Field(default="imported", index=True)
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ImportedGateResult(WorkspaceOwned, table=True):
    __tablename__ = "imported_gate_results"
    __table_args__ = (UniqueConstraint("workspace_id", "gate_result_id", name="uq_gate_results_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    gate_result_id: str = Field(index=True)
    send_intent_id: Optional[int] = Field(default=None, foreign_key="send_intents.id", index=True)
    external_intent_id: str = Field(index=True)
    status: str = Field(index=True)
    checks_json: str = Field(default="[]", sa_column=Column(Text))
    reasons_json: str = Field(default="[]", sa_column=Column(Text))
    external_reservation_id: Optional[str] = Field(default=None, index=True)
    evaluated_at: datetime
    policy_snapshot_id: Optional[int] = Field(default=None, foreign_key="policy_snapshots.id", index=True)
    external_policy_id: Optional[str] = Field(default=None, index=True)
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    imported_at: datetime = Field(default_factory=utc_now)


class SendReservation(WorkspaceOwned, table=True):
    __tablename__ = "send_reservations"
    __table_args__ = (
        Index(
            "uq_send_reservations_active_recipient",
            text("coalesce(workspace_id, 0)"),
            "normalized_recipient_email",
            unique=True,
            postgresql_where=text(
                "dedupe_recipient = true AND status IN ('active', 'reserved', 'attempting_provider_send', 'outcome_uncertain')"
            ),
            sqlite_where=text(
                "dedupe_recipient = 1 AND status IN ('active', 'reserved', 'attempting_provider_send', 'outcome_uncertain')"
            ),
        ),
        Index(
            "uq_send_reservations_active_company",
            text("coalesce(workspace_id, 0)"),
            "company_policy_key",
            unique=True,
            postgresql_where=text(
                "dedupe_company = true AND status IN ('active', 'reserved', 'attempting_provider_send', 'outcome_uncertain')"
            ),
            sqlite_where=text(
                "dedupe_company = 1 AND status IN ('active', 'reserved', 'attempting_provider_send', 'outcome_uncertain')"
            ),
        ),
        UniqueConstraint("workspace_id", "reservation_id", name="uq_send_reservations_workspace_external_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    reservation_id: str = Field(index=True)
    send_intent_id: Optional[int] = Field(default=None, foreign_key="send_intents.id", index=True)
    normalized_recipient_email: str = Field(index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    company_policy_key: str = Field(index=True)
    policy_snapshot_id: Optional[int] = Field(default=None, foreign_key="policy_snapshots.id", index=True)
    status: str = Field(index=True)
    dedupe_recipient: bool = Field(default=True, index=True)
    dedupe_company: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=utc_now)
    released_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    notes_json: str = Field(default="{}", sa_column=Column(Text))


class OutreachRecord(WorkspaceOwned, table=True):
    __tablename__ = "outreach_records"
    __table_args__ = (UniqueConstraint("workspace_id", "outreach_record_id", name="uq_outreach_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    outreach_record_id: str = Field(index=True)
    send_intent_id: Optional[int] = Field(default=None, foreign_key="send_intents.id", index=True)
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    contact_id: Optional[int] = Field(default=None, foreign_key="contacts.id", index=True)
    normalized_recipient_email: str = Field(index=True)
    company_policy_key: str = Field(index=True)
    policy_snapshot_id: Optional[int] = Field(default=None, foreign_key="policy_snapshots.id", index=True)
    channel: str = Field(default="email", index=True)
    status: str = Field(index=True)
    dedupe_recipient: bool = Field(default=True, index=True)
    dedupe_company: bool = Field(default=True, index=True)
    occurred_at: datetime = Field(default_factory=utc_now)
    source: str = Field(default="backend", index=True)
    notes_json: str = Field(default="{}", sa_column=Column(Text))


class CompanyIdentity(WorkspaceOwned, table=True):
    __tablename__ = "company_identities"
    __table_args__ = (
        UniqueConstraint("workspace_id", "identity_id", name="uq_company_identities_workspace_external_id"),
        UniqueConstraint("workspace_id", "canonical_company_policy_key", name="uq_company_identities_workspace_policy_key"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    identity_id: str = Field(index=True)
    canonical_company_policy_key: str = Field(index=True)
    display_name: str
    normalized_name: str = Field(index=True)
    primary_domain: Optional[str] = Field(default=None, index=True)
    confidence: float = Field(default=1.0, sa_column=Column(Float))
    needs_review: bool = Field(default=False, index=True)
    source: str = Field(default="backend", index=True)
    notes_json: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CompanyIdentityAlias(WorkspaceOwned, table=True):
    __tablename__ = "company_identity_aliases"
    __table_args__ = (UniqueConstraint("workspace_id", "alias_id", name="uq_company_aliases_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    alias_id: str = Field(index=True)
    identity_id: Optional[int] = Field(default=None, foreign_key="company_identities.id", index=True)
    alias_type: str = Field(index=True)
    alias_value: str = Field(index=True)
    normalized_value: str = Field(index=True)
    confidence: float = Field(default=1.0, sa_column=Column(Float))
    needs_review: bool = Field(default=False, index=True)
    source: str = Field(default="backend", index=True)
    notes_json: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)


class SendApprovalSnapshot(WorkspaceOwned, table=True):
    __tablename__ = "send_approval_snapshots"
    __table_args__ = (UniqueConstraint("workspace_id", "approval_id", name="uq_send_approvals_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    approval_id: str = Field(index=True)
    batch_id: str = Field(index=True)
    send_intent_id: Optional[int] = Field(default=None, foreign_key="send_intents.id", index=True)
    external_intent_id: str = Field(index=True)
    reviewer_id: str = Field(index=True)
    status: str = Field(default="approved", index=True)
    normalized_recipient_email: str = Field(index=True)
    raw_recipient_email: str
    subject: str
    body_text: str = Field(sa_column=Column(Text))
    body_html: Optional[str] = Field(default=None, sa_column=Column(Text))
    company_id: Optional[int] = Field(default=None, foreign_key="companies.id", index=True)
    company_policy_key: str = Field(index=True)
    company_identity_key: str = Field(index=True)
    policy_snapshot_id: Optional[int] = Field(default=None, foreign_key="policy_snapshots.id", index=True)
    user_profile_snapshot_id: Optional[int] = Field(default=None, foreign_key="user_profile_snapshots.id", index=True)
    master_cv_profile_snapshot_id: Optional[int] = Field(default=None, foreign_key="master_cv_profile_snapshots.id", index=True)
    email_draft_id: Optional[int] = Field(default=None, foreign_key="email_drafts.id", index=True)
    payload_hash: str = Field(index=True)
    attachments_json: str = Field(default="[]", sa_column=Column(Text))
    source_refs_json: str = Field(default="[]", sa_column=Column(Text))
    claim_refs_json: str = Field(default="[]", sa_column=Column(Text))
    frozen_json: str = Field(sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)


class SentMessage(WorkspaceOwned, table=True):
    __tablename__ = "sent_messages"
    __table_args__ = (UniqueConstraint("workspace_id", "sent_message_id", name="uq_sent_messages_workspace_external_id"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    sent_message_id: str = Field(index=True)
    approval_snapshot_id: Optional[int] = Field(default=None, foreign_key="send_approval_snapshots.id", index=True)
    send_intent_id: Optional[int] = Field(default=None, foreign_key="send_intents.id", index=True)
    reservation_id: Optional[int] = Field(default=None, foreign_key="send_reservations.id", index=True)
    provider: str = Field(index=True)
    provider_message_id: Optional[str] = Field(default=None, index=True)
    provider_thread_id: Optional[str] = Field(default=None, index=True)
    status: str = Field(index=True)
    normalized_recipient_email: str = Field(index=True)
    company_policy_key: str = Field(index=True)
    network_performed: bool = Field(default=False, index=True)
    provider_response_json: str = Field(default="{}", sa_column=Column(Text))
    error_json: str = Field(default="{}", sa_column=Column(Text))
    created_at: datetime = Field(default_factory=utc_now)
    accepted_at: Optional[datetime] = None
