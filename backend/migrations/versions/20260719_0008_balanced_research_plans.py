"""add balanced research planning and coverage persistence

Revision ID: 20260719_0008
Revises: 20260715_0007
Create Date: 2026-07-19 17:00:00.000000
"""

from alembic import op
import sqlalchemy as sa

from backend.app.db import models


revision = "20260719_0008"
down_revision = "20260715_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("research_plans", "research_targets", "research_search_attempts", "research_discoveries"):
        models.SQLModel.metadata.tables[name].create(op.get_bind(), checkfirst=True)
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("job_postings")}
    indexes = {index["name"] for index in inspector.get_indexes("job_postings")}
    with op.batch_alter_table("job_postings") as batch:
        if "work_mode" not in columns:
            batch.add_column(sa.Column("work_mode", sa.String(), nullable=False, server_default="unknown"))
        if "remote_regions_json" not in columns:
            batch.add_column(sa.Column("remote_regions_json", sa.Text(), nullable=False, server_default="[]"))
        if "duration_min_weeks" not in columns:
            batch.add_column(sa.Column("duration_min_weeks", sa.Integer(), nullable=True))
        if "duration_max_weeks" not in columns:
            batch.add_column(sa.Column("duration_max_weeks", sa.Integer(), nullable=True))
        if "ix_job_postings_work_mode" not in indexes:
            batch.create_index("ix_job_postings_work_mode", ["work_mode"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Destructive downgrade is intentionally unsupported for research planning data.")
