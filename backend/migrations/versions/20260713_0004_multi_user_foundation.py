"""add multi-user ownership and workflow foundation

Revision ID: 20260713_0004
Revises: 20260525_0003
Create Date: 2026-07-13 12:00:00.000000
"""

from __future__ import annotations

from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa

from backend.app.db import models


revision = "20260713_0004"
down_revision = "20260525_0003"
branch_labels = None
depends_on = None


OWNED_TABLES = (
    "runs",
    "imported_files",
    "validation_results",
    "audit_logs",
    "user_profile_snapshots",
    "master_cv_profile_snapshots",
    "policy_snapshots",
    "companies",
    "contacts",
    "fit_evaluations",
    "email_drafts",
    "send_intents",
    "imported_gate_results",
    "send_reservations",
    "outreach_records",
    "company_identities",
    "company_identity_aliases",
    "send_approval_snapshots",
    "sent_messages",
)

NEW_CORE_TABLES = (
    "users",
    "workspaces",
    "invitations",
    "auth_sessions",
    "oauth_states",
    "gmail_connections",
    "admin_access_audits",
)

NEW_OWNED_TABLES = (
    "onboarding_sessions",
    "campaign_companies",
    "agent_tasks",
    "review_exceptions",
    "documents",
)

EXTERNAL_ID_INDEXES = {
    "runs": ("run_id", "uq_runs_workspace_external_id"),
    "user_profile_snapshots": ("profile_id", "uq_user_profiles_workspace_external_id"),
    "master_cv_profile_snapshots": ("profile_id", "uq_master_cv_profiles_workspace_external_id"),
    "policy_snapshots": ("policy_id", "uq_policies_workspace_external_id"),
    "companies": ("company_id", "uq_companies_workspace_external_id"),
    "contacts": ("contact_id", "uq_contacts_workspace_external_id"),
    "fit_evaluations": ("evaluation_id", "uq_fit_evaluations_workspace_external_id"),
    "email_drafts": ("draft_id", "uq_email_drafts_workspace_external_id"),
    "send_intents": ("intent_id", "uq_send_intents_workspace_external_id"),
    "imported_gate_results": ("gate_result_id", "uq_gate_results_workspace_external_id"),
    "send_reservations": ("reservation_id", "uq_send_reservations_workspace_external_id"),
    "outreach_records": ("outreach_record_id", "uq_outreach_workspace_external_id"),
    "company_identities": ("identity_id", "uq_company_identities_workspace_external_id"),
    "company_identity_aliases": ("alias_id", "uq_company_aliases_workspace_external_id"),
    "send_approval_snapshots": ("approval_id", "uq_send_approvals_workspace_external_id"),
    "sent_messages": ("sent_message_id", "uq_sent_messages_workspace_external_id"),
}


def _create_model_table(name: str) -> None:
    models.SQLModel.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def _create_campaigns_table() -> None:
    """Create the 0004 campaign shape without depending on future models.

    This migration predates the Master CV document table. Using the live
    SQLModel metadata here would make a fresh migration attempt to create that
    future foreign key before its referenced table exists.
    """

    op.create_table(
        "campaigns",
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("campaign_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("sending_mode", sa.String(), nullable=False),
        sa.Column("brief_json", sa.Text(), nullable=True),
        sa.Column("user_profile_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("master_cv_profile_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("policy_snapshot_id", sa.Integer(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("paused_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.ForeignKeyConstraint(
            ["user_profile_snapshot_id"],
            ["user_profile_snapshots.id"],
        ),
        sa.ForeignKeyConstraint(
            ["master_cv_profile_snapshot_id"],
            ["master_cv_profile_snapshots.id"],
        ),
        sa.ForeignKeyConstraint(["policy_snapshot_id"], ["policy_snapshots.id"]),
        sa.UniqueConstraint(
            "workspace_id",
            "campaign_id",
            name="uq_campaigns_workspace_external_id",
        ),
    )
    for column_name in (
        "workspace_id",
        "campaign_id",
        "status",
        "sending_mode",
        "user_profile_snapshot_id",
        "master_cv_profile_snapshot_id",
        "policy_snapshot_id",
    ):
        op.create_index(
            f"ix_campaigns_{column_name}",
            "campaigns",
            [column_name],
            unique=False,
        )


def upgrade() -> None:
    for table_name in NEW_CORE_TABLES:
        _create_model_table(table_name)

    now = datetime.now(timezone.utc)
    users = models.User.__table__
    workspaces = models.Workspace.__table__
    bind = op.get_bind()
    user_result = bind.execute(
        users.insert().values(
            google_subject="bootstrap:legacy",
            email="legacy@local.invalid",
            display_name="Legacy administrator",
            role="admin",
            status="pending",
            created_at=now,
            updated_at=now,
        )
    )
    user_id = user_result.inserted_primary_key[0]
    workspace_result = bind.execute(
        workspaces.insert().values(
            workspace_id="workspace-legacy",
            owner_user_id=user_id,
            name="Legacy workspace",
            status="active",
            created_at=now,
            updated_at=now,
        )
    )
    workspace_id = workspace_result.inserted_primary_key[0]

    for table_name in OWNED_TABLES:
        with op.batch_alter_table(table_name) as batch:
            batch.add_column(sa.Column("workspace_id", sa.Integer(), nullable=True))
        op.execute(sa.text(f"UPDATE {table_name} SET workspace_id = :workspace_id").bindparams(workspace_id=workspace_id))
        with op.batch_alter_table(table_name) as batch:
            batch.alter_column("workspace_id", nullable=False)
            batch.create_foreign_key(f"fk_{table_name}_workspace_id", "workspaces", ["workspace_id"], ["id"])
            batch.create_index(f"ix_{table_name}_workspace_id", ["workspace_id"], unique=False)

    for table_name, (column_name, constraint_name) in EXTERNAL_ID_INDEXES.items():
        op.drop_index(f"ix_{table_name}_{column_name}", table_name=table_name)
        op.create_index(f"ix_{table_name}_{column_name}", table_name, [column_name], unique=False)
        op.create_index(constraint_name, table_name, ["workspace_id", column_name], unique=True)

    op.drop_index("ix_company_identities_canonical_company_policy_key", table_name="company_identities")
    op.create_index(
        "ix_company_identities_canonical_company_policy_key",
        "company_identities",
        ["canonical_company_policy_key"],
        unique=False,
    )
    op.create_index(
        "uq_company_identities_workspace_policy_key",
        "company_identities",
        ["workspace_id", "canonical_company_policy_key"],
        unique=True,
    )

    op.drop_index("uq_send_reservations_active_recipient", table_name="send_reservations")
    op.drop_index("uq_send_reservations_active_company", table_name="send_reservations")
    op.create_index(
        "uq_send_reservations_active_recipient",
        "send_reservations",
        ["workspace_id", "normalized_recipient_email"],
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
        ["workspace_id", "company_policy_key"],
        unique=True,
        postgresql_where=sa.text(
            "dedupe_company = true AND status IN ('active', 'reserved', 'attempting_provider_send', 'outcome_uncertain')"
        ),
        sqlite_where=sa.text(
            "dedupe_company = 1 AND status IN ('active', 'reserved', 'attempting_provider_send', 'outcome_uncertain')"
        ),
    )

    _create_campaigns_table()
    for table_name in NEW_OWNED_TABLES:
        _create_model_table(table_name)


def downgrade() -> None:
    raise NotImplementedError("Destructive downgrade is intentionally unsupported for the multi-user migration.")
