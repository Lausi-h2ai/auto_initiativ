from __future__ import annotations

import json
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine, select

from backend.app.db.models import AgentTask, AuditLog, Campaign, ResearchTarget
from backend.app.research.planning import (
    compile_research_plan,
    confirm_plan,
    replace_pending_plan,
)
from backend.app.workflow.engine import WorkflowEngine
from backend.app.workflow.research_graph import (
    observe_plan_confirmed,
    observe_target_launch,
    observe_target_reconciled,
)
from backend.app.workflow.shadow_readiness import (
    VerificationEvidence,
    collect_shadow_evidence,
    evaluate_shadow_readiness,
)


SCHEMA = Path("schemas/research_plan.schema.json")


def _campaign(
    session: Session,
    *,
    campaign_type: str,
    suffix: str,
) -> tuple[Campaign, list[ResearchTarget]]:
    campaign = Campaign(
        workspace_id=1,
        campaign_id=f"shadow-scenario-{suffix}",
        name=f"Shadow scenario {suffix}",
        campaign_type=campaign_type,
        status="researching",
        brief_json=json.dumps(
            {
                "role_focus": "Applied AI",
                "locations": ["Zurich", "Basel"],
                "search_breadth": "balanced",
                "max_companies": 30,
                "max_jobs": 30,
                "time_budget_minutes": 30,
            }
        ),
    )
    session.add(campaign)
    session.flush()
    plan = replace_pending_plan(
        session,
        campaign,
        compile_research_plan(campaign, schema_path=SCHEMA),
    )
    confirm_plan(plan)
    session.add(plan)
    session.flush()
    observe_plan_confirmed(session, campaign=campaign, plan=plan)
    targets = session.exec(
        select(ResearchTarget)
        .where(ResearchTarget.research_plan_id == plan.id)
        .order_by(ResearchTarget.id)
    ).all()
    return campaign, targets


def _observe_guaranteed_execution(
    session: Session,
    *,
    campaign: Campaign,
    target: ResearchTarget,
    suffix: str,
) -> None:
    task_type = (
        "job_research_target"
        if campaign.campaign_type == "listed_job_search"
        else "company_research_target"
    )
    task = AgentTask(
        workspace_id=campaign.workspace_id,
        campaign_id=campaign.id,
        task_id=f"shadow-task-{suffix}",
        agent_role=(
            "vacancy_scout"
            if campaign.campaign_type == "listed_job_search"
            else "company_researcher"
        ),
        task_type=task_type,
        status="completed",
        input_json=json.dumps(
            {
                "research_target_id": target.id,
                "target_id": target.target_id,
                "budget_phase": "guaranteed",
            },
            sort_keys=True,
        ),
    )
    session.add(task)
    session.flush()
    observe_target_launch(
        session,
        task=task,
        target=target,
        campaign=campaign,
    )
    observe_target_reconciled(
        session,
        task=task,
        target=target,
        campaign=campaign,
    )


def test_deterministic_scenario_matrix_covers_the_shadow_contract(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'shadow-scenarios.db'}")
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        initiative, initiative_targets = _campaign(
            session,
            campaign_type="initiative_outreach",
            suffix="initiative",
        )
        listed, listed_targets = _campaign(
            session,
            campaign_type="listed_job_search",
            suffix="listed",
        )

        terminal_states = (
            (initiative_targets[0], "covered"),
            (initiative_targets[1], "exhausted"),
            (listed_targets[0], "covered"),
            (listed_targets[1], "failed"),
        )
        for index, (target, status) in enumerate(terminal_states):
            campaign = initiative if target.campaign_id == initiative.id else listed
            target.status = status
            target.completed_attempts = target.required_attempts
            target.consumed_time_seconds = 60
            target.reserved_time_seconds = 0
            session.add(target)
            _observe_guaranteed_execution(
                session,
                campaign=campaign,
                target=target,
                suffix=str(index),
            )
        session.commit()

        workflow = WorkflowEngine(session)
        assert workflow._maybe_schedule_shared_research(initiative) is True
        session.flush()
        shared_tasks = session.exec(
            select(AgentTask).where(
                AgentTask.campaign_id == initiative.id,
                AgentTask.input_json.contains('"budget_phase": "shared"'),
            )
        ).all()
        assert len(shared_tasks) == 2
        shared_pairs: list[tuple[AgentTask, ResearchTarget]] = []
        for index, shared_task in enumerate(shared_tasks):
            shared_target_id = json.loads(shared_task.input_json)[
                "research_target_id"
            ]
            shared_target = session.get(ResearchTarget, shared_target_id)
            assert shared_target is not None
            observe_target_launch(
                session,
                task=shared_task,
                target=shared_target,
                campaign=initiative,
            )
            shared_task.status = "completed"
            shared_target.status = "covered" if index == 0 else "exhausted"
            shared_target.reserved_time_seconds = 0
            session.add_all([shared_task, shared_target])
            observe_target_reconciled(
                session,
                task=shared_task,
                target=shared_target,
                campaign=initiative,
            )
            shared_pairs.append((shared_task, shared_target))
        session.commit()

        workflow._maybe_finalize_balanced_campaign(initiative)
        workflow._maybe_finalize_balanced_campaign(listed)
        session.commit()

        # Replaying observation calls must not inflate the evidence set.
        replay_task, replay_target = shared_pairs[0]
        observe_target_launch(
            session,
            task=replay_task,
            target=replay_target,
            campaign=initiative,
        )
        observe_target_reconciled(
            session,
            task=replay_task,
            target=replay_target,
            campaign=initiative,
        )
        session.commit()

        report = evaluate_shadow_readiness(
            collect_shadow_evidence(
                session,
                verification=VerificationEvidence(
                    postgres_concurrency="passed",
                    crash_recovery="passed",
                    workspace_isolation_and_cancellation="passed",
                ),
            )
        )
        events = session.exec(
            select(AuditLog).where(
                AuditLog.entity_type == "workflow_graph_shadow_event"
            )
        ).all()

    assert report.verdict == "ready"
    assert report.gaps == []
    assert report.mismatches == []
    assert report.coverage.campaign_kinds == [
        "initiative_outreach",
        "listed_job_search",
    ]
    assert report.coverage.terminal_target_states == [
        "covered",
        "exhausted",
        "failed",
    ]
    assert report.coverage.max_targets_per_graph_run == 2
    assert report.coverage.shared_lease_generations == [1]
    assert report.summary["executions"] == 6
    assert len({event.entity_id for event in events}) == len(events)
