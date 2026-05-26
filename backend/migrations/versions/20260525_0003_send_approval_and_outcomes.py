"""add send approval snapshots and provider outcomes

Revision ID: 20260525_0003
Revises: 20260514_0002
Create Date: 2026-05-25 09:30:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision = "20260525_0003"
down_revision = "20260514_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("uq_outreach_records_contacted_recipient", table_name="outreach_records")
    op.drop_index("uq_outreach_records_contacted_company", table_name="outreach_records")
    op.drop_index("uq_send_reservations_active_recipient", table_name="send_reservations")
    op.drop_index("uq_send_reservations_active_company", table_name="send_reservations")
    op.create_index(
        "uq_send_reservations_active_recipient",
        "send_reservations",
        ["normalized_recipient_email"],
        unique=True,
        postgresql_where=sa.text(
            "dedupe_recipient = true AND status IN ('active', 'reserved', 'attempting_provider_send', 'outcome_uncertain')"
        ),
        sqlite_where=sa.text(
            "dedupe_recipient = 1 AND status IN ('active', 'reserved', 'attempting_provider_send', 'outcome_uncertain')"
        ),
    )
    op.create_index(
        "uq_send_reservations_active_company",
        "send_reservations",
        ["company_policy_key"],
        unique=True,
        postgresql_where=sa.text(
            "dedupe_company = true AND status IN ('active', 'reserved', 'attempting_provider_send', 'outcome_uncertain')"
        ),
        sqlite_where=sa.text(
            "dedupe_company = 1 AND status IN ('active', 'reserved', 'attempting_provider_send', 'outcome_uncertain')"
        ),
    )

    op.create_table(
        "company_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("identity_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("canonical_company_policy_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("display_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("normalized_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("primary_domain", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("notes_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_company_identities_identity_id"), "company_identities", ["identity_id"], unique=True)
    op.create_index(
        op.f("ix_company_identities_canonical_company_policy_key"),
        "company_identities",
        ["canonical_company_policy_key"],
        unique=True,
    )
    op.create_index(op.f("ix_company_identities_normalized_name"), "company_identities", ["normalized_name"])
    op.create_index(op.f("ix_company_identities_primary_domain"), "company_identities", ["primary_domain"])
    op.create_index(op.f("ix_company_identities_needs_review"), "company_identities", ["needs_review"])
    op.create_index(op.f("ix_company_identities_source"), "company_identities", ["source"])

    op.create_table(
        "company_identity_aliases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("alias_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("identity_id", sa.Integer(), nullable=True),
        sa.Column("alias_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("alias_value", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("normalized_value", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("needs_review", sa.Boolean(), nullable=False),
        sa.Column("source", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("notes_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["identity_id"], ["company_identities.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_company_identity_aliases_alias_id"), "company_identity_aliases", ["alias_id"], unique=True)
    op.create_index(op.f("ix_company_identity_aliases_identity_id"), "company_identity_aliases", ["identity_id"])
    op.create_index(op.f("ix_company_identity_aliases_alias_type"), "company_identity_aliases", ["alias_type"])
    op.create_index(op.f("ix_company_identity_aliases_alias_value"), "company_identity_aliases", ["alias_value"])
    op.create_index(op.f("ix_company_identity_aliases_normalized_value"), "company_identity_aliases", ["normalized_value"])
    op.create_index(op.f("ix_company_identity_aliases_needs_review"), "company_identity_aliases", ["needs_review"])
    op.create_index(op.f("ix_company_identity_aliases_source"), "company_identity_aliases", ["source"])

    op.create_table(
        "send_approval_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("approval_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("batch_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("send_intent_id", sa.Integer(), nullable=True),
        sa.Column("external_intent_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("reviewer_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("normalized_recipient_email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("raw_recipient_email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("subject", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("company_id", sa.Integer(), nullable=True),
        sa.Column("company_policy_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("company_identity_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("policy_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("user_profile_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("master_cv_profile_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("email_draft_id", sa.Integer(), nullable=True),
        sa.Column("payload_hash", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("attachments_json", sa.Text(), nullable=False),
        sa.Column("source_refs_json", sa.Text(), nullable=False),
        sa.Column("claim_refs_json", sa.Text(), nullable=False),
        sa.Column("frozen_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.ForeignKeyConstraint(["email_draft_id"], ["email_drafts.id"]),
        sa.ForeignKeyConstraint(["master_cv_profile_snapshot_id"], ["master_cv_profile_snapshots.id"]),
        sa.ForeignKeyConstraint(["policy_snapshot_id"], ["policy_snapshots.id"]),
        sa.ForeignKeyConstraint(["send_intent_id"], ["send_intents.id"]),
        sa.ForeignKeyConstraint(["user_profile_snapshot_id"], ["user_profile_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name in (
        "approval_id",
        "batch_id",
        "send_intent_id",
        "external_intent_id",
        "reviewer_id",
        "status",
        "normalized_recipient_email",
        "company_id",
        "company_policy_key",
        "company_identity_key",
        "policy_snapshot_id",
        "user_profile_snapshot_id",
        "master_cv_profile_snapshot_id",
        "email_draft_id",
        "payload_hash",
    ):
        op.create_index(op.f(f"ix_send_approval_snapshots_{name}"), "send_approval_snapshots", [name], unique=name == "approval_id")

    op.create_table(
        "sent_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("sent_message_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("approval_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("send_intent_id", sa.Integer(), nullable=True),
        sa.Column("reservation_id", sa.Integer(), nullable=True),
        sa.Column("provider", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("provider_message_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("provider_thread_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("normalized_recipient_email", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("company_policy_key", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("network_performed", sa.Boolean(), nullable=False),
        sa.Column("provider_response_json", sa.Text(), nullable=False),
        sa.Column("error_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("accepted_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["approval_snapshot_id"], ["send_approval_snapshots.id"]),
        sa.ForeignKeyConstraint(["reservation_id"], ["send_reservations.id"]),
        sa.ForeignKeyConstraint(["send_intent_id"], ["send_intents.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for name in (
        "sent_message_id",
        "approval_snapshot_id",
        "send_intent_id",
        "reservation_id",
        "provider",
        "provider_message_id",
        "provider_thread_id",
        "status",
        "normalized_recipient_email",
        "company_policy_key",
        "network_performed",
    ):
        op.create_index(op.f(f"ix_sent_messages_{name}"), "sent_messages", [name], unique=name == "sent_message_id")


def downgrade() -> None:
    raise NotImplementedError("Destructive downgrade of send approval/outcome tables is intentionally disabled.")
