from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, Float, Index, Text, text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Run(SQLModel, table=True):
    __tablename__ = "runs"

    id: Optional[int] = Field(default=None, primary_key=True)
    run_id: str = Field(index=True, unique=True)
    agent_type: Optional[str] = None
    output_path: str
    status: str = Field(index=True)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ImportedFile(SQLModel, table=True):
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


class ValidationResult(SQLModel, table=True):
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


class AuditLog(SQLModel, table=True):
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


class UserProfileSnapshot(SQLModel, table=True):
    __tablename__ = "user_profile_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: str = Field(index=True, unique=True)
    schema_version: str
    source_created_at: Optional[datetime] = None
    source_updated_at: Optional[datetime] = None
    content_hash: str = Field(index=True)
    status: str = Field(default="imported", index=True)
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    imported_at: datetime = Field(default_factory=utc_now)


class MasterCvProfileSnapshot(SQLModel, table=True):
    __tablename__ = "master_cv_profile_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    profile_id: str = Field(index=True, unique=True)
    schema_version: str
    source_created_at: Optional[datetime] = None
    content_hash: str = Field(index=True)
    status: str = Field(default="imported", index=True)
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    imported_at: datetime = Field(default_factory=utc_now)


class PolicySnapshot(SQLModel, table=True):
    __tablename__ = "policy_snapshots"

    id: Optional[int] = Field(default=None, primary_key=True)
    policy_id: str = Field(index=True, unique=True)
    schema_version: str
    source_created_at: Optional[datetime] = None
    content_hash: str = Field(index=True)
    status: str = Field(default="imported", index=True)
    raw_json: str = Field(sa_column=Column(Text))
    imported_file_id: Optional[int] = Field(default=None, foreign_key="imported_files.id")
    imported_at: datetime = Field(default_factory=utc_now)


class Company(SQLModel, table=True):
    __tablename__ = "companies"

    id: Optional[int] = Field(default=None, primary_key=True)
    company_id: str = Field(index=True, unique=True)
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


class Contact(SQLModel, table=True):
    __tablename__ = "contacts"

    id: Optional[int] = Field(default=None, primary_key=True)
    contact_id: str = Field(index=True, unique=True)
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


class FitEvaluation(SQLModel, table=True):
    __tablename__ = "fit_evaluations"

    id: Optional[int] = Field(default=None, primary_key=True)
    evaluation_id: str = Field(index=True, unique=True)
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


class EmailDraft(SQLModel, table=True):
    __tablename__ = "email_drafts"

    id: Optional[int] = Field(default=None, primary_key=True)
    draft_id: str = Field(index=True, unique=True)
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


class SendIntent(SQLModel, table=True):
    __tablename__ = "send_intents"

    id: Optional[int] = Field(default=None, primary_key=True)
    intent_id: str = Field(index=True, unique=True)
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


class ImportedGateResult(SQLModel, table=True):
    __tablename__ = "imported_gate_results"

    id: Optional[int] = Field(default=None, primary_key=True)
    gate_result_id: str = Field(index=True, unique=True)
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


class SendReservation(SQLModel, table=True):
    __tablename__ = "send_reservations"
    __table_args__ = (
        Index(
            "uq_send_reservations_active_recipient",
            "normalized_recipient_email",
            unique=True,
            postgresql_where=text("dedupe_recipient = true AND status IN ('active', 'reserved')"),
            sqlite_where=text("dedupe_recipient = 1 AND status IN ('active', 'reserved')"),
        ),
        Index(
            "uq_send_reservations_active_company",
            "company_policy_key",
            unique=True,
            postgresql_where=text("dedupe_company = true AND status IN ('active', 'reserved')"),
            sqlite_where=text("dedupe_company = 1 AND status IN ('active', 'reserved')"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    reservation_id: str = Field(index=True, unique=True)
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


class OutreachRecord(SQLModel, table=True):
    __tablename__ = "outreach_records"
    __table_args__ = (
        Index(
            "uq_outreach_records_contacted_recipient",
            "normalized_recipient_email",
            unique=True,
            postgresql_where=text("dedupe_recipient = true AND status IN ('sent', 'delivered', 'contacted')"),
            sqlite_where=text("dedupe_recipient = 1 AND status IN ('sent', 'delivered', 'contacted')"),
        ),
        Index(
            "uq_outreach_records_contacted_company",
            "company_policy_key",
            unique=True,
            postgresql_where=text("dedupe_company = true AND status IN ('sent', 'delivered', 'contacted')"),
            sqlite_where=text("dedupe_company = 1 AND status IN ('sent', 'delivered', 'contacted')"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    outreach_record_id: str = Field(index=True, unique=True)
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
