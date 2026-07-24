from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.db.models import AgentTask


def _task(task_id: str, *, workspace_id: int, execution_key: str | None = None) -> AgentTask:
    return AgentTask(
        workspace_id=workspace_id,
        task_id=task_id,
        agent_role="company_researcher",
        task_type="company_research",
        execution_key=execution_key,
    )


def test_agent_task_graph_fields_default_and_persist(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'graph-fields.db'}")
    SQLModel.metadata.create_all(engine)

    task = _task("task-graph-fields", workspace_id=1, execution_key="execution-1")
    assert task.graph_definition_id is None
    assert task.graph_version is None
    assert task.graph_run_id is None
    assert task.node_id is None
    assert task.parent_execution_ids_json == "[]"

    task.graph_definition_id = "coordinated_research"
    task.graph_version = 1
    task.graph_run_id = "graph-run-1"
    task.node_id = "research_target"
    task.parent_execution_ids_json = '["execution-parent"]'

    with Session(engine) as session:
        session.add(task)
        session.commit()

    with Session(engine) as session:
        stored = session.exec(
            select(AgentTask).where(AgentTask.task_id == "task-graph-fields")
        ).one()

    assert stored.graph_definition_id == "coordinated_research"
    assert stored.graph_version == 1
    assert stored.graph_run_id == "graph-run-1"
    assert stored.node_id == "research_target"
    assert stored.execution_key == "execution-1"
    assert stored.parent_execution_ids_json == '["execution-parent"]'


def test_execution_key_is_unique_within_workspace_and_isolated_across_workspaces(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'execution-key.db'}")
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        session.add(_task("task-first", workspace_id=1, execution_key="shared-key"))
        session.commit()

        session.add(_task("task-duplicate", workspace_id=1, execution_key="shared-key"))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(_task("task-other-workspace", workspace_id=2, execution_key="shared-key"))
        session.add(_task("task-legacy-null-1", workspace_id=1))
        session.add(_task("task-legacy-null-2", workspace_id=1))
        session.commit()

        tasks = session.exec(select(AgentTask)).all()

    assert {task.task_id for task in tasks} == {
        "task-first",
        "task-other-workspace",
        "task-legacy-null-1",
        "task-legacy-null-2",
    }
