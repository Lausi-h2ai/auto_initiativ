from __future__ import annotations

import os
import threading
from datetime import timedelta
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, create_engine, select

from backend.app.auth.context import RequestIdentity, workspace_context
from backend.app.core.config import Settings, get_settings
from backend.app.db import session as db_session_module
from backend.app.db.models import (
    AgentTask,
    Campaign,
    ReviewException,
    User,
    Workspace,
    utc_now,
)
from backend.app.product.routes import pause_campaign
from backend.app.workflow.engine import (
    WORKFLOW_TASK_LEASE_SECONDS,
    WorkflowEngine,
    WorkflowWorker,
)


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
    with Session(postgres_engine) as session:
        persisted = session.get(AgentTask, task.id)
        assert persisted is not None
        persisted.status = "completed"
        session.add(persisted)
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
        claimed.status = "completed"
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


def test_postgres_expired_lease_is_reconciled_exactly_once(
    postgres_engine,
    monkeypatch,
):
    task = _queued_task(postgres_engine)
    with Session(postgres_engine) as session:
        persisted = session.get(AgentTask, task.id)
        assert persisted is not None
        persisted.status = "running"
        persisted.run_id = f"runtime-{persisted.task_id}"
        persisted.locked_by = "terminated-worker"
        persisted.locked_at = utc_now() - timedelta(
            seconds=WORKFLOW_TASK_LEASE_SECONDS + 1
        )
        session.add(persisted)
        session.commit()

    reconciliations: list[str] = []
    reconciliation_lock = threading.Lock()
    start = threading.Barrier(2)

    def fake_reconcile(self, claimed: AgentTask) -> None:
        with reconciliation_lock:
            reconciliations.append(claimed.task_id)
        claimed.status = "completed"
        claimed.locked_by = None
        claimed.locked_at = None
        self.session.add(claimed)
        self.session.commit()

    monkeypatch.setattr(WorkflowEngine, "reconcile", fake_reconcile)
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
    assert reconciliations == [task.task_id]
    assert results.count(True) == 1
    with Session(postgres_engine) as session:
        persisted = session.get(AgentTask, task.id)
        assert persisted is not None
        assert persisted.status == "completed"


def test_postgres_uncertain_expired_launch_blocks_without_relaunch(
    postgres_engine,
    monkeypatch,
):
    task = _queued_task(postgres_engine)
    with Session(postgres_engine) as session:
        persisted = session.get(AgentTask, task.id)
        assert persisted is not None
        persisted.status = "running"
        persisted.locked_by = "terminated-before-runtime-id"
        persisted.locked_at = utc_now() - timedelta(
            seconds=WORKFLOW_TASK_LEASE_SECONDS + 1
        )
        session.add(persisted)
        session.commit()

    monkeypatch.setattr(
        WorkflowEngine,
        "process",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("uncertain external work must never relaunch")
        ),
    )
    settings = Settings(
        database_url=str(postgres_engine.url),
        workflow_worker_enabled=False,
    )

    assert WorkflowWorker(settings).run_once() is True
    with Session(postgres_engine) as session:
        persisted = session.get(AgentTask, task.id)
        exception = session.exec(
            select(ReviewException).where(
                ReviewException.agent_task_id == task.id
            )
        ).one()
        assert persisted is not None
        assert persisted.status == "blocked"
        assert persisted.locked_by is None
        assert exception.category == "uncertain_external_launch"


def test_postgres_pause_is_workspace_isolated_and_preserves_running_work(
    postgres_engine,
):
    suffix = uuid4().hex
    records: list[dict[str, int | str]] = []
    with Session(postgres_engine) as session:
        for index in range(2):
            user = User(
                google_subject=f"pause-{index}-{suffix}",
                email=f"pause-{index}-{suffix}@example.com",
                display_name=f"Pause {index}",
            )
            session.add(user)
            session.flush()
            workspace = Workspace(
                workspace_id=f"pause-{index}-{suffix}",
                owner_user_id=user.id,
                name=f"Pause {index}",
            )
            session.add(workspace)
            session.flush()
            campaign = Campaign(
                workspace_id=workspace.id,
                campaign_id=f"pause-campaign-{index}-{suffix}",
                name=f"Pause campaign {index}",
                status="researching",
            )
            session.add(campaign)
            session.flush()
            queued = AgentTask(
                workspace_id=workspace.id,
                campaign_id=campaign.id,
                task_id=f"pause-queued-{index}-{suffix}",
                agent_role="company_researcher",
                task_type="company_research_target",
                status="queued",
            )
            running = AgentTask(
                workspace_id=workspace.id,
                campaign_id=campaign.id,
                task_id=f"pause-running-{index}-{suffix}",
                agent_role="company_researcher",
                task_type="company_research_target",
                status="running",
                run_id=f"pause-runtime-{index}-{suffix}",
                locked_by="active-worker",
                locked_at=utc_now(),
            )
            session.add_all([queued, running])
            session.flush()
            records.append(
                {
                    "user_id": user.id,
                    "workspace_id": workspace.id,
                    "campaign_id": campaign.id,
                    "campaign_public_id": campaign.campaign_id,
                    "queued_id": queued.id,
                    "running_id": running.id,
                }
            )
        session.commit()

    first = records[0]
    second = records[1]
    identity = RequestIdentity(
        user_id=int(first["user_id"]),
        workspace_id=int(first["workspace_id"]),
    )
    with workspace_context(identity), Session(postgres_engine) as session:
        assert session.exec(
            select(Campaign).where(
                Campaign.campaign_id == str(second["campaign_public_id"])
            )
        ).first() is None
        response = pause_campaign(str(first["campaign_public_id"]), session)
        assert response["status"] == "paused"

    with Session(postgres_engine) as session:
        assert session.get(Campaign, int(first["campaign_id"])).status == "paused"
        assert session.get(AgentTask, int(first["queued_id"])).status == "paused"
        assert session.get(AgentTask, int(first["running_id"])).status == "running"
        assert session.get(Campaign, int(second["campaign_id"])).status == "researching"
        assert session.get(AgentTask, int(second["queued_id"])).status == "queued"
        assert session.get(AgentTask, int(second["running_id"])).status == "running"

        # Leave no active work behind for other tests sharing the disposable DB.
        for record in records:
            persisted_campaign = session.get(
                Campaign,
                int(record["campaign_id"]),
            )
            persisted_queued = session.get(
                AgentTask,
                int(record["queued_id"]),
            )
            persisted_running = session.get(
                AgentTask,
                int(record["running_id"]),
            )
            assert persisted_campaign is not None
            assert persisted_queued is not None
            assert persisted_running is not None
            persisted_campaign.status = "completed"
            persisted_queued.status = "completed"
            persisted_running.status = "completed"
            session.add_all(
                [persisted_campaign, persisted_queued, persisted_running]
            )
        session.commit()
