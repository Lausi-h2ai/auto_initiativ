"""add master CV builder persistence

Revision ID: 20260715_0006
Revises: 20260714_0005
Create Date: 2026-07-15 12:00:00.000000
"""

from alembic import op

from backend.app.db import models


revision = "20260715_0006"
down_revision = "20260714_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("profile_assets", "master_cv_document_snapshots", "master_cv_builder_sessions"):
        models.SQLModel.metadata.tables[name].create(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise NotImplementedError("Destructive downgrade is intentionally unsupported for master CV data.")
