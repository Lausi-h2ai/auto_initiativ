"""pin campaign Master CV document foundations

Revision ID: 20260715_0007
Revises: 20260715_0006
Create Date: 2026-07-15 16:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260715_0007"
down_revision = "20260715_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns("campaigns")}
    indexes = {index["name"] for index in inspector.get_indexes("campaigns")}
    with op.batch_alter_table("campaigns") as batch:
        if "master_cv_document_snapshot_id" not in columns:
            batch.add_column(sa.Column("master_cv_document_snapshot_id", sa.Integer(), nullable=True))
            batch.create_foreign_key(
                "fk_campaigns_master_cv_document_snapshot_id",
                "master_cv_document_snapshots", ["master_cv_document_snapshot_id"], ["id"],
            )
        if "ix_campaigns_master_cv_document_snapshot_id" not in indexes:
            batch.create_index("ix_campaigns_master_cv_document_snapshot_id", ["master_cv_document_snapshot_id"], unique=False)
    _add_columns("profile_assets", {
        "original_relative_path": sa.Column("original_relative_path", sa.Text(), nullable=True),
        "variants_json": sa.Column("variants_json", sa.Text(), nullable=False, server_default="[]"),
        "processing_metadata_json": sa.Column("processing_metadata_json", sa.Text(), nullable=False, server_default="{}"),
        "inclusion_policy": sa.Column("inclusion_policy", sa.String(), nullable=False, server_default="german_swiss"),
        "active_version": sa.Column("active_version", sa.Integer(), nullable=False, server_default="1"),
    })
    _add_columns("master_cv_document_snapshots", {
        "user_profile_snapshot_id": sa.Column("user_profile_snapshot_id", sa.Integer(), nullable=True),
        "template_version": sa.Column("template_version", sa.String(), nullable=False, server_default="1.0"),
        "market": sa.Column("market", sa.String(), nullable=False, server_default="international"),
        "page_goal": sa.Column("page_goal", sa.Integer(), nullable=False, server_default="1"),
        "portrait_variant_id": sa.Column("portrait_variant_id", sa.String(), nullable=True),
        "review_flags_json": sa.Column("review_flags_json", sa.Text(), nullable=False, server_default="[]"),
        "renderer_version": sa.Column("renderer_version", sa.String(), nullable=False, server_default="1.0"),
    }, foreign_keys=(("fk_master_cv_documents_user_profile_snapshot_id", "user_profile_snapshot_id", "user_profile_snapshots", "id"),))
    _add_columns("master_cv_builder_sessions", {
        "current_candidate_snapshot_id": sa.Column("current_candidate_snapshot_id", sa.Integer(), nullable=True),
        "selected_entry_route": sa.Column("selected_entry_route", sa.String(), nullable=False, server_default="approved_profile"),
        "candidate_revision": sa.Column("candidate_revision", sa.Integer(), nullable=False, server_default="1"),
    }, foreign_keys=(("fk_master_cv_sessions_current_candidate_snapshot_id", "current_candidate_snapshot_id", "master_cv_document_snapshots", "id"),))


def _add_columns(
    table_name: str,
    wanted: dict[str, sa.Column],
    *,
    foreign_keys: tuple[tuple[str, str, str, str], ...] = (),
) -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {column["name"] for column in inspector.get_columns(table_name)}
    existing_fk_columns = {tuple(item.get("constrained_columns") or ()) for item in inspector.get_foreign_keys(table_name)}
    with op.batch_alter_table(table_name) as batch:
        for name, column in wanted.items():
            if name not in existing:
                batch.add_column(column)
        for constraint_name, local_column, remote_table, remote_column in foreign_keys:
            if (local_column,) not in existing_fk_columns:
                batch.create_foreign_key(constraint_name, remote_table, [local_column], [remote_column])


def downgrade() -> None:
    raise NotImplementedError("Destructive downgrade is intentionally unsupported for campaign foundations.")
