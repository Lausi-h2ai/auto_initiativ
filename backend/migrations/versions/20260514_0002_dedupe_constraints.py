"""add phase 2 dedupe constraints

Revision ID: 20260514_0002
Revises: 0176dbbb5e28
Create Date: 2026-05-14 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260514_0002"
down_revision: str | None = "0176dbbb5e28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "send_reservations",
        sa.Column("dedupe_recipient", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "send_reservations",
        sa.Column("dedupe_company", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index(
        op.f("ix_send_reservations_dedupe_recipient"),
        "send_reservations",
        ["dedupe_recipient"],
        unique=False,
    )
    op.create_index(
        op.f("ix_send_reservations_dedupe_company"),
        "send_reservations",
        ["dedupe_company"],
        unique=False,
    )
    op.create_index(
        "uq_send_reservations_active_recipient",
        "send_reservations",
        ["normalized_recipient_email"],
        unique=True,
        postgresql_where=sa.text("dedupe_recipient = true AND status IN ('active', 'reserved')"),
        sqlite_where=sa.text("dedupe_recipient = 1 AND status IN ('active', 'reserved')"),
    )
    op.create_index(
        "uq_send_reservations_active_company",
        "send_reservations",
        ["company_policy_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_company = true AND status IN ('active', 'reserved')"),
        sqlite_where=sa.text("dedupe_company = 1 AND status IN ('active', 'reserved')"),
    )

    op.add_column(
        "outreach_records",
        sa.Column("dedupe_recipient", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.add_column(
        "outreach_records",
        sa.Column("dedupe_company", sa.Boolean(), server_default=sa.true(), nullable=False),
    )
    op.create_index(
        op.f("ix_outreach_records_dedupe_recipient"),
        "outreach_records",
        ["dedupe_recipient"],
        unique=False,
    )
    op.create_index(
        op.f("ix_outreach_records_dedupe_company"),
        "outreach_records",
        ["dedupe_company"],
        unique=False,
    )
    op.create_index(
        "uq_outreach_records_contacted_recipient",
        "outreach_records",
        ["normalized_recipient_email"],
        unique=True,
        postgresql_where=sa.text("dedupe_recipient = true AND status IN ('sent', 'delivered', 'contacted')"),
        sqlite_where=sa.text("dedupe_recipient = 1 AND status IN ('sent', 'delivered', 'contacted')"),
    )
    op.create_index(
        "uq_outreach_records_contacted_company",
        "outreach_records",
        ["company_policy_key"],
        unique=True,
        postgresql_where=sa.text("dedupe_company = true AND status IN ('sent', 'delivered', 'contacted')"),
        sqlite_where=sa.text("dedupe_company = 1 AND status IN ('sent', 'delivered', 'contacted')"),
    )


def downgrade() -> None:
    raise NotImplementedError("Destructive downgrade of Phase 2 dedupe constraints is intentionally disabled.")
