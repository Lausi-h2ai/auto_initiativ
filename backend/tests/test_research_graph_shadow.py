import json

from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.db.models import AgentTask, AuditLog, Campaign, ResearchPlan, ResearchTarget
from backend.app.research.planning import plan_hash
from backend.app.workflow.research_graph import (
    graph_run_id_for,
    observe_target_launch,
    observe_target_reconciled,
    target_execution_key_for,
)


def _rows(session: Session, *, confirmed: bool = True, schema_version: str = "1.1"):
    campaign = Campaign(
        campaign_id="campaign-shadow",
        name="Shadow",
        campaign_type="initiative_outreach",
        workspace_id=7,
    )
    session.add(campaign)
    session.flush()
    raw = {"schema_version": schema_version, "targets": []}
    digest = plan_hash(raw)
    plan = ResearchPlan(
        plan_id="plan-shadow",
        campaign_id=campaign.id,
        version=3,
        status="confirmed" if confirmed else "pending_confirmation",
        content_hash=digest,
        confirmed_hash=digest if confirmed else None,
        raw_json=json.dumps(raw),
        workspace_id=7,
    )
    session.add(plan)
    session.flush()
    target = ResearchTarget(
        research_plan_id=plan.id,
        campaign_id=campaign.id,
        target_id="target-zurich",
        label="Zurich",
        target_kind="geographic",
        normalized_value="zurich",
        workspace_id=7,
    )
    session.add(target)
    session.flush()
    task = AgentTask(
        task_id="task-shadow",
        campaign_id=campaign.id,
        task_type="company_research_target",
        agent_role="company_researcher",
        input_json=json.dumps(
            {
                "research_target_id": target.id,
                "budget_phase": "guaranteed",
            }
        ),
        workspace_id=7,
    )
    session.add(task)
    session.flush()
    return campaign, target, task


def test_shadow_identities_are_stable_and_include_generation() -> None:
    run = graph_run_id_for(
        workspace_id=7,
        campaign_id="campaign-shadow",
        plan_version=3,
        confirmed_plan_hash="abc",
    )
    assert run == graph_run_id_for(
        workspace_id=7,
        campaign_id="campaign-shadow",
        plan_version=3,
        confirmed_plan_hash="abc",
    )
    assert target_execution_key_for(
        graph_run_id=run,
        target_id="target-zurich",
        budget_phase="shared",
        logical_generation=1,
    ) != target_execution_key_for(
        graph_run_id=run,
        target_id="target-zurich",
        budget_phase="shared",
        logical_generation=2,
    )


def test_launch_annotation_and_reconcile_audits_are_replay_idempotent(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'shadow.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign, target, task = _rows(session)
        first = observe_target_launch(session, task=task, target=target, campaign=campaign)
        observe_target_reconciled(session, task=task, target=target, campaign=campaign)
        session.commit()
        observe_target_launch(session, task=task, target=target, campaign=campaign)
        observe_target_reconciled(session, task=task, target=target, campaign=campaign)
        session.commit()

        assert first is not None
        assert task.graph_definition_id == "coordinated_research"
        assert task.graph_version == 1
        assert task.node_id == "research_target"
        assert task.execution_key == first.execution_key
        audits = session.exec(
            select(AuditLog).where(AuditLog.entity_type == "workflow_graph_shadow_event")
        ).all()
        assert len(audits) == 8
        assert all(json.loads(row.metadata_json)["shadow_mode"] is True for row in audits)


def test_legacy_or_unconfirmed_plan_is_not_annotated(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign, target, task = _rows(session, confirmed=False)
        assert observe_target_launch(
            session, task=task, target=target, campaign=campaign
        ) is None
        assert task.execution_key is None
        assert session.exec(select(AuditLog)).all() == []


def test_shared_lease_uses_explicit_generation_and_edge(tmp_path) -> None:
    engine = create_engine(f"sqlite:///{tmp_path / 'shared.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        campaign, target, task = _rows(session)
        task.input_json = json.dumps(
            {
                "research_target_id": target.id,
                "budget_phase": "shared",
                "lease_generation": 2,
            }
        )
        target.shared_lease_count = 2

        correlation = observe_target_launch(
            session,
            task=task,
            target=target,
            campaign=campaign,
        )
        session.commit()

        assert correlation is not None
        assert correlation.budget_phase == "shared"
        assert correlation.logical_generation == 2
        audit = session.exec(
            select(AuditLog).where(
                AuditLog.action == "workflow_graph_shadow_transition_observed"
            )
        ).one()
        metadata = json.loads(audit.metadata_json)
        assert metadata["edge_id"] == "shared_budget_lease"
        assert metadata["logical_generation"] == 2
