"""add campaign-wide research budget tracking

Revision ID: 20260720_0010
Revises: 20260719_0009
Create Date: 2026-07-20 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260720_0010"
down_revision = "20260719_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("research_targets")}
    additions = (
        ("guaranteed_candidate_goal", sa.Integer(), "0"),
        ("guaranteed_time_seconds", sa.Integer(), "0"),
        ("consumed_time_seconds", sa.Integer(), "0"),
        ("reserved_time_seconds", sa.Integer(), "0"),
        ("shared_lease_count", sa.Integer(), "0"),
    )
    with op.batch_alter_table("research_targets") as batch:
        for name, column_type, default in additions:
            if name not in columns:
                batch.add_column(sa.Column(name, column_type, nullable=False, server_default=default))


def downgrade() -> None:
    raise NotImplementedError("Destructive downgrade is intentionally unsupported for research budget data.")
