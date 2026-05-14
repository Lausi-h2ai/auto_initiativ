"""create phase 1 operational tables

Revision ID: 20260513_0001
Revises:
Create Date: 2026-05-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "20260513_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("agent_type", sa.String(), nullable=True),
        sa.Column("output_path", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_runs_run_id", "runs", ["run_id"], unique=True)
    op.create_index("ix_runs_status", "runs", ["status"], unique=False)

    op.create_table(
        "imported_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("schema_name", sa.String(), nullable=True),
        sa.Column("sha256", sa.String(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("raw_json", sa.Text(), nullable=True),
        sa.Column("imported_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_imported_files_filename", "imported_files", ["filename"], unique=False)
    op.create_index("ix_imported_files_run_id", "imported_files", ["run_id"], unique=False)
    op.create_index("ix_imported_files_schema_name", "imported_files", ["schema_name"], unique=False)
    op.create_index("ix_imported_files_status", "imported_files", ["status"], unique=False)

    op.create_table(
        "validation_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("imported_file_id", sa.Integer(), nullable=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("schema_name", sa.String(), nullable=True),
        sa.Column("error_count", sa.Integer(), nullable=False),
        sa.Column("errors_json", sa.Text(), nullable=True),
        sa.Column("reason_codes_json", sa.Text(), nullable=True),
        sa.Column("validated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["imported_file_id"], ["imported_files.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_validation_results_filename", "validation_results", ["filename"], unique=False)
    op.create_index("ix_validation_results_run_id", "validation_results", ["run_id"], unique=False)
    op.create_index("ix_validation_results_schema_name", "validation_results", ["schema_name"], unique=False)
    op.create_index("ix_validation_results_status", "validation_results", ["status"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("actor_type", sa.String(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("result_status", sa.String(), nullable=False),
        sa.Column("reason_codes_json", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"], unique=False)
    op.create_index("ix_audit_logs_actor_type", "audit_logs", ["actor_type"], unique=False)
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"], unique=False)
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"], unique=False)
    op.create_index("ix_audit_logs_result_status", "audit_logs", ["result_status"], unique=False)
    op.create_index("ix_audit_logs_run_id", "audit_logs", ["run_id"], unique=False)


def downgrade() -> None:
    raise NotImplementedError("Destructive downgrade of Phase 1 operational tables is intentionally disabled.")
