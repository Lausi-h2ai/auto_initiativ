from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from backend.app.core.config import Settings
from backend.app.db import session as db_session_module
from backend.app.db.models import AgentTask, ReviewException, User, Workspace, utc_now
from backend.app.workflow.engine import WORKFLOW_TASK_LEASE_SECONDS, WorkflowEngine, WorkflowWorker


def _task(db_session: Session, *, status: str = "queued", run_id: str | None = None) -> AgentTask:
    user = User(google_subject="claim-user", email="claim@example.com", display_name="Claim User")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    workspace = Workspace(workspace_id="claim-workspace", owner_user_id=user.id, name="Claims")
    db_session.add(workspace)
    db_session.commit()
    db_session.refresh(workspace)
    task = AgentTask(
        workspace_id=workspace.id,
        task_id="task-claim",
        agent_role="company_researcher",
        task_type="company_research",
        status=status,
        run_id=run_id,
    )
    db_session.add(task)
    db_session.commit()
    db_session.refresh(task)
    return task


def _settings(database_url: str) -> Settings:
    return Settings(database_url=database_url, workflow_worker_enabled=False)


def test_competing_workers_only_launch_a_queued_task_once(
    db_session: Session, database_url: str, monkeypatch
) -> None:
    task = _task(db_session)
    launches: list[str] = []

    def fake_process(self, claimed: AgentTask, *, already_claimed: bool = False) -> None:
        assert already_claimed is True
        launches.append(claimed.task_id)
        claimed.run_id = "external-run"
        self.session.add(claimed)
        self.session.commit()

    monkeypatch.setattr(WorkflowEngine, "process", fake_process)
    db_session_module.engine = db_session.get_bind()
    first = WorkflowWorker(_settings(database_url))
    second = WorkflowWorker(_settings(database_url))

    assert first.run_once() is True
    assert second.run_once() is False
    assert launches == [task.task_id]


def test_new_claim_launches_before_it_can_be_reconciled(
    db_session: Session, database_url: str, monkeypatch
) -> None:
    _task(db_session)
    calls: list[str] = []

    def fake_process(self, claimed: AgentTask, *, already_claimed: bool = False) -> None:
        calls.append("launch")
        claimed.run_id = "external-run"
        self.session.add(claimed)
        self.session.commit()

    def fake_reconcile(self, claimed: AgentTask) -> None:
        calls.append("reconcile")

    monkeypatch.setattr(WorkflowEngine, "process", fake_process)
    monkeypatch.setattr(WorkflowEngine, "reconcile", fake_reconcile)
    db_session_module.engine = db_session.get_bind()
    worker = WorkflowWorker(_settings(database_url))

    assert worker.run_once() is True
    assert calls == ["launch"]
    assert worker.run_once() is True
    assert calls == ["launch", "reconcile"]


def test_expired_running_lease_is_reclaimed_and_renewed(
    db_session: Session, database_url: str, monkeypatch
) -> None:
    task = _task(db_session, status="running", run_id="external-run")
    task.locked_by = "dead-worker"
    task.locked_at = utc_now() - timedelta(seconds=WORKFLOW_TASK_LEASE_SECONDS + 1)
    db_session.add(task)
    db_session.commit()
    reconciled: list[str] = []

    def fake_reconcile(self, claimed: AgentTask) -> None:
        reconciled.append(claimed.task_id)

    monkeypatch.setattr(WorkflowEngine, "reconcile", fake_reconcile)
    db_session_module.engine = db_session.get_bind()
    worker = WorkflowWorker(_settings(database_url))

    assert worker.run_once() is True
    db_session.expire_all()
    refreshed = db_session.get(AgentTask, task.id)
    assert reconciled == [task.task_id]
    assert refreshed.locked_by == worker.worker_id
    renewed_at = refreshed.locked_at
    if renewed_at.tzinfo is None:
        renewed_at = renewed_at.replace(tzinfo=utc_now().tzinfo)
    assert renewed_at > utc_now() - timedelta(seconds=5)


def test_expired_claim_without_run_id_is_blocked_not_relaunched(
    db_session: Session, database_url: str, monkeypatch
) -> None:
    task = _task(db_session, status="running")
    task.locked_by = "dead-worker"
    task.locked_at = utc_now() - timedelta(seconds=WORKFLOW_TASK_LEASE_SECONDS + 1)
    db_session.add(task)
    db_session.commit()
    monkeypatch.setattr(
        WorkflowEngine,
        "process",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("must not relaunch")),
    )
    db_session_module.engine = db_session.get_bind()

    assert WorkflowWorker(_settings(database_url)).run_once() is True
    db_session.expire_all()
    refreshed = db_session.get(AgentTask, task.id)
    exception = db_session.exec(
        select(ReviewException).where(ReviewException.agent_task_id == task.id)
    ).one()
    assert refreshed.status == "blocked"
    assert refreshed.locked_by is None
    assert exception.category == "uncertain_external_launch"
