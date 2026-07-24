from __future__ import annotations

import os
import threading
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine

from backend.app.core.config import Settings, get_settings
from backend.app.db import session as db_session_module
from backend.app.db.models import AgentTask, User, Workspace
from backend.app.workflow.engine import WorkflowEngine, WorkflowWorker


PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


@pytest.fixture()
def postgres_engine(monkeypatch):
    database_url = os.environ.get("POSTGRES_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("POSTGRES_TEST_DATABASE_URL is not configured.")
    monkeypatch.setenv("DATABASE_URL", database_url)
    get_settings.cache_clear()
    command.upgrade(Config(os.path.join(PROJECT_ROOT, "alembic.ini")), "head")
    engine = create_engine(database_url)
    db_session_module.engine = engine
    return engine


def _queued_task(postgres_engine) -> AgentTask:
    suffix = uuid4().hex
    with Session(postgres_engine) as session:
        user = User(
            google_subject=f"workflow-{suffix}",
            email=f"workflow-{suffix}@example.com",
            display_name="Workflow Test",
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        workspace = Workspace(
            workspace_id=f"workflow-{suffix}",
            owner_user_id=user.id,
            name="Workflow Test",
        )
        session.add(workspace)
        session.commit()
        session.refresh(workspace)
        task = AgentTask(
            workspace_id=workspace.id,
            task_id=f"task-{suffix}",
            execution_key=f"execution-{suffix}",
            agent_role="company_researcher",
            task_type="company_research",
            status="queued",
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        session.expunge(task)
        return task


def test_postgres_execution_key_is_unique_per_workspace(postgres_engine):
    task = _queued_task(postgres_engine)
    with pytest.raises(IntegrityError):
        with Session(postgres_engine) as session:
            session.add(
                AgentTask(
                    workspace_id=task.workspace_id,
                    task_id=f"duplicate-{uuid4().hex}",
                    execution_key=task.execution_key,
                    agent_role="company_researcher",
                    task_type="company_research",
                )
            )
            session.commit()


def test_postgres_competing_workers_launch_exactly_once(
    postgres_engine,
    monkeypatch,
):
    task = _queued_task(postgres_engine)
    launches: list[str] = []
    launches_lock = threading.Lock()
    start = threading.Barrier(2)

    def fake_process(
        self,
        claimed: AgentTask,
        *,
        already_claimed: bool = False,
    ) -> None:
        assert already_claimed is True
        with launches_lock:
            launches.append(claimed.task_id)
        claimed.run_id = f"runtime-{claimed.task_id}"
        self.session.add(claimed)
        self.session.commit()

    monkeypatch.setattr(WorkflowEngine, "process", fake_process)
    settings = Settings(
        database_url=str(postgres_engine.url),
        workflow_worker_enabled=False,
    )
    workers = [WorkflowWorker(settings), WorkflowWorker(settings)]
    results: list[bool] = []

    def run(worker: WorkflowWorker) -> None:
        start.wait()
        results.append(worker.run_once())

    threads = [threading.Thread(target=run, args=(worker,)) for worker in workers]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert all(not thread.is_alive() for thread in threads)
    assert launches == [task.task_id]
    assert any(results)
