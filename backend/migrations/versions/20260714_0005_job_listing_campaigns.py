"""add verified job listing campaigns

Revision ID: 20260714_0005
Revises: 20260713_0004
Create Date: 2026-07-14 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

from backend.app.db import models


revision = "20260714_0005"
down_revision = "20260713_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    campaign_columns = {column["name"] for column in inspector.get_columns("campaigns")}
    campaign_indexes = {index["name"] for index in inspector.get_indexes("campaigns")}
    with op.batch_alter_table("campaigns") as batch:
        if "campaign_type" not in campaign_columns:
            batch.add_column(sa.Column("campaign_type", sa.String(), nullable=False, server_default="initiative_outreach"))
        if "ix_campaigns_campaign_type" not in campaign_indexes:
            batch.create_index("ix_campaigns_campaign_type", ["campaign_type"], unique=False)
    for name in ("job_postings", "campaign_jobs", "job_fit_evaluations", "job_application_packages", "job_source_trust"):
        models.SQLModel.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise NotImplementedError("Destructive downgrade is intentionally unsupported for job listing campaigns.")
