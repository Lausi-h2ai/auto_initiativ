"""add agent task graph correlation and idempotency

Revision ID: 20260724_0011
Revises: 20260720_0010
Create Date: 2026-07-24 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


revision = "20260724_0011"
down_revision = "20260720_0010"
branch_labels = None
depends_on = None


TABLE_NAME = "agent_tasks"
EXECUTION_KEY_CONSTRAINT = "uq_agent_tasks_workspace_execution_key"
GRAPH_RUN_INDEX = "ix_agent_tasks_workspace_graph_run"
GRAPH_NODE_INDEX = "ix_agent_tasks_workspace_graph_node"
GRAPH_COLUMNS = (
    "graph_definition_id",
    "graph_version",
    "graph_run_id",
    "node_id",
    "execution_key",
    "parent_execution_ids_json",
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(TABLE_NAME)
        if constraint.get("name")
    }
    indexes = {index["name"] for index in inspector.get_indexes(TABLE_NAME)}

    with op.batch_alter_table(TABLE_NAME) as batch:
        if "graph_definition_id" not in columns:
            batch.add_column(sa.Column("graph_definition_id", sa.String(), nullable=True))
        if "graph_version" not in columns:
            batch.add_column(sa.Column("graph_version", sa.Integer(), nullable=True))
        if "graph_run_id" not in columns:
            batch.add_column(sa.Column("graph_run_id", sa.String(), nullable=True))
        if "node_id" not in columns:
            batch.add_column(sa.Column("node_id", sa.String(), nullable=True))
        if "execution_key" not in columns:
            batch.add_column(sa.Column("execution_key", sa.String(), nullable=True))
        if "parent_execution_ids_json" not in columns:
            batch.add_column(
                sa.Column(
                    "parent_execution_ids_json",
                    sa.Text(),
                    nullable=False,
                    server_default="[]",
                )
            )
        if EXECUTION_KEY_CONSTRAINT not in unique_constraints:
            batch.create_unique_constraint(
                EXECUTION_KEY_CONSTRAINT,
                ["workspace_id", "execution_key"],
            )
        if GRAPH_RUN_INDEX not in indexes:
            batch.create_index(
                GRAPH_RUN_INDEX,
                ["workspace_id", "graph_run_id"],
                unique=False,
            )
        if GRAPH_NODE_INDEX not in indexes:
            batch.create_index(
                GRAPH_NODE_INDEX,
                ["workspace_id", "graph_run_id", "node_id"],
                unique=False,
            )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    columns = {column["name"] for column in inspector.get_columns(TABLE_NAME)}
    unique_constraints = {
        constraint["name"]
        for constraint in inspector.get_unique_constraints(TABLE_NAME)
        if constraint.get("name")
    }
    indexes = {index["name"] for index in inspector.get_indexes(TABLE_NAME)}

    with op.batch_alter_table(TABLE_NAME) as batch:
        if GRAPH_NODE_INDEX in indexes:
            batch.drop_index(GRAPH_NODE_INDEX)
        if GRAPH_RUN_INDEX in indexes:
            batch.drop_index(GRAPH_RUN_INDEX)
        if EXECUTION_KEY_CONSTRAINT in unique_constraints:
            batch.drop_constraint(EXECUTION_KEY_CONSTRAINT, type_="unique")
        for column_name in reversed(GRAPH_COLUMNS):
            if column_name in columns:
                batch.drop_column(column_name)
