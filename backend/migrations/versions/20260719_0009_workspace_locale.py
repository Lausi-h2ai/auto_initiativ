"""add workspace locale preference

Revision ID: 20260719_0009
Revises: 20260719_0008
Create Date: 2026-07-19 19:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260719_0009"
down_revision = "20260719_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("workspaces")}
    indexes = {index["name"] for index in inspector.get_indexes("workspaces")}
    with op.batch_alter_table("workspaces") as batch:
        if "locale" not in columns:
            batch.add_column(sa.Column("locale", sa.String(), nullable=False, server_default="en"))
        if "ix_workspaces_locale" not in indexes:
            batch.create_index("ix_workspaces_locale", ["locale"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Destructive downgrade is intentionally unsupported for workspace preferences.")
