from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from backend.app.core.config import get_settings


PROJECT_ROOT = Path(__file__).resolve().parents[2]
GRAPH_REVISION = "20260724_0011"
PREVIOUS_REVISION = "20260720_0010"
GRAPH_COLUMNS = {
    "graph_definition_id",
    "graph_version",
    "graph_run_id",
    "node_id",
    "execution_key",
    "parent_execution_ids_json",
}


def _alembic_config() -> Config:
    return Config(str(PROJECT_ROOT / "alembic.ini"))


def test_graph_correlation_migration_upgrades_existing_tasks_and_downgrades_cleanly(
    tmp_path,
    monkeypatch,
):
    database_url = f"sqlite:///{tmp_path / 'graph-migration.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    config = _alembic_config()
    engine = create_engine(database_url)

    command.upgrade(config, PREVIOUS_REVISION)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO agent_tasks (
                    workspace_id, task_id, agent_role, task_type, status, progress,
                    narrative, input_json, output_json, attempt_count, max_attempts,
                    available_at, created_at, updated_at
                ) VALUES (
                    1, 'legacy-task', 'company_researcher', 'company_research',
                    'queued', 0, 'Queued', '{}', '{}', 0, 3,
                    CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )

    command.upgrade(config, GRAPH_REVISION)
    inspector = inspect(engine)
    columns = {column["name"]: column for column in inspector.get_columns("agent_tasks")}
    constraints = {
        constraint["name"]: constraint
        for constraint in inspector.get_unique_constraints("agent_tasks")
    }
    indexes = {index["name"] for index in inspector.get_indexes("agent_tasks")}

    assert GRAPH_COLUMNS.issubset(columns)
    assert columns["parent_execution_ids_json"]["nullable"] is False
    assert constraints["uq_agent_tasks_workspace_execution_key"]["column_names"] == [
        "workspace_id",
        "execution_key",
    ]
    assert "ix_agent_tasks_workspace_graph_run" in indexes
    assert "ix_agent_tasks_workspace_graph_node" in indexes
    with engine.connect() as connection:
        parent_ids = connection.execute(
            text(
                "SELECT parent_execution_ids_json FROM agent_tasks "
                "WHERE task_id = 'legacy-task'"
            )
        ).scalar_one()
    assert parent_ids == "[]"

    command.downgrade(config, PREVIOUS_REVISION)
    remaining_columns = {
        column["name"] for column in inspect(engine).get_columns("agent_tasks")
    }
    assert GRAPH_COLUMNS.isdisjoint(remaining_columns)
