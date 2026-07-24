"""Shadow correlation for the coordinated-research graph.

This module observes the existing workflow engine.  It must not select routes,
allocate budget, mutate task status, or invoke an agent runtime.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from sqlmodel import Session, select

from backend.app.db.models import AgentTask, AuditLog, Campaign, ResearchPlan, ResearchTarget
from backend.app.workflow.graph import (
    COORDINATED_RESEARCH_REGISTRY,
    WorkflowDefinition,
    coordinated_research_v1,
    validate_workflow_definition,
)


COORDINATED_RESEARCH_DEFINITION: WorkflowDefinition = coordinated_research_v1()
validate_workflow_definition(
    COORDINATED_RESEARCH_DEFINITION,
    COORDINATED_RESEARCH_REGISTRY,
)

TARGET_TASK_TYPES = frozenset({"company_research_target", "job_research_target"})
SUPPORTED_CAMPAIGN_TYPES = frozenset({"initiative_outreach", "listed_job_search"})


@dataclass(frozen=True, slots=True)
class ResearchGraphCorrelation:
    graph_run_id: str
    execution_key: str
    budget_phase: str
    logical_generation: int
    plan_id: int
    plan_version: int
    plan_hash: str


def _stable_id(prefix: str, *parts: object) -> str:
    encoded = "\x1f".join(str(part) for part in parts).encode("utf-8")
    return f"{prefix}-{hashlib.sha256(encoded).hexdigest()}"


def graph_run_id_for(
    *,
    workspace_id: int,
    campaign_id: str,
    plan_version: int,
    confirmed_plan_hash: str,
) -> str:
    """Return the stable identity of one confirmed-plan graph run."""

    return _stable_id(
        "graph-run",
        workspace_id,
        campaign_id,
        plan_version,
        confirmed_plan_hash,
    )


def target_execution_key_for(
    *,
    graph_run_id: str,
    target_id: str,
    budget_phase: str,
    logical_generation: int,
) -> str:
    """Return the deterministic identity of a target-agent execution."""

    return _stable_id(
        "graph-exec",
        graph_run_id,
        "research_target",
        target_id,
        budget_phase,
        logical_generation,
    )


def _confirmed_plan(
    session: Session,
    *,
    task: AgentTask,
    target: ResearchTarget,
    campaign: Campaign,
) -> ResearchPlan | None:
    if (
        task.task_type not in TARGET_TASK_TYPES
        or task.workspace_id is None
        or campaign.id is None
        or campaign.workspace_id != task.workspace_id
        or target.workspace_id != task.workspace_id
        or target.campaign_id != campaign.id
        or campaign.campaign_type not in SUPPORTED_CAMPAIGN_TYPES
    ):
        return None
    plan = session.exec(
        select(ResearchPlan).where(
            ResearchPlan.id == target.research_plan_id,
            ResearchPlan.campaign_id == campaign.id,
            ResearchPlan.workspace_id == task.workspace_id,
        )
    ).first()
    if (
        plan is None
        or plan.id is None
        or plan.status != "confirmed"
        or not plan.confirmed_hash
        or plan.confirmed_hash != plan.content_hash
    ):
        return None
    try:
        raw_plan = json.loads(plan.raw_json)
    except (TypeError, json.JSONDecodeError):
        return None
    if not isinstance(raw_plan, dict) or raw_plan.get("schema_version") != "1.1":
        return None
    calculated_hash = hashlib.sha256(
        json.dumps(raw_plan, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if calculated_hash != plan.content_hash:
        return None
    return plan


def correlate_target_task(
    session: Session,
    *,
    task: AgentTask,
    target: ResearchTarget,
    campaign: Campaign,
    logical_generation: int | None = None,
) -> ResearchGraphCorrelation | None:
    """Attach shadow metadata when the task belongs to an intact v1.1 plan.

    Existing conflicting metadata or an execution-key collision is left
    untouched.  This keeps correlation strictly observational.
    """

    plan = _confirmed_plan(session, task=task, target=target, campaign=campaign)
    if plan is None or task.workspace_id is None:
        return None
    payload = _json_object(task.input_json)
    budget_phase = str(payload.get("budget_phase") or "guaranteed")
    if budget_phase not in {"guaranteed", "shared"}:
        return None
    if logical_generation is None:
        raw_generation = payload.get("lease_generation")
        if raw_generation is None:
            logical_generation = target.shared_lease_count if budget_phase == "shared" else 0
        elif isinstance(raw_generation, int) and raw_generation >= 0:
            logical_generation = raw_generation
        else:
            return None
    if logical_generation < 0:
        return None

    graph_run_id = graph_run_id_for(
        workspace_id=task.workspace_id,
        campaign_id=campaign.campaign_id,
        plan_version=plan.version,
        confirmed_plan_hash=plan.confirmed_hash,
    )
    execution_key = target_execution_key_for(
        graph_run_id=graph_run_id,
        target_id=target.target_id,
        budget_phase=budget_phase,
        logical_generation=logical_generation,
    )
    expected = (
        COORDINATED_RESEARCH_DEFINITION.definition_id,
        COORDINATED_RESEARCH_DEFINITION.version,
        graph_run_id,
        "research_target",
        execution_key,
    )
    current = (
        task.graph_definition_id,
        task.graph_version,
        task.graph_run_id,
        task.node_id,
        task.execution_key,
    )
    if any(value is not None for value in current) and current != expected:
        return None
    collision = session.exec(
        select(AgentTask).where(
            AgentTask.workspace_id == task.workspace_id,
            AgentTask.execution_key == execution_key,
        )
    ).first()
    if collision is not None and collision.id != task.id:
        return None

    task.graph_definition_id = expected[0]
    task.graph_version = expected[1]
    task.graph_run_id = expected[2]
    task.node_id = expected[3]
    task.execution_key = expected[4]
    task.parent_execution_ids_json = task.parent_execution_ids_json or "[]"
    session.add(task)
    return ResearchGraphCorrelation(
        graph_run_id=graph_run_id,
        execution_key=execution_key,
        budget_phase=budget_phase,
        logical_generation=logical_generation,
        plan_id=plan.id,
        plan_version=plan.version,
        plan_hash=plan.confirmed_hash,
    )


def observe_target_launch(
    session: Session,
    *,
    task: AgentTask,
    target: ResearchTarget,
    campaign: Campaign,
    logical_generation: int | None = None,
) -> ResearchGraphCorrelation | None:
    correlation = correlate_target_task(
        session,
        task=task,
        target=target,
        campaign=campaign,
        logical_generation=logical_generation,
    )
    if correlation is None:
        return None
    edge_id = (
        "shared_budget_lease"
        if correlation.budget_phase == "shared"
        else "targets_materialized"
    )
    reason_code = (
        "bounded_shared_budget_lease_allocated"
        if correlation.budget_phase == "shared"
        else "research_target_materialized"
    )
    _record_event(
        session,
        correlation=correlation,
        task=task,
        target=target,
        campaign=campaign,
        event_kind="transition",
        node_id="research_target",
        edge_id=edge_id,
        reason_code=reason_code,
    )
    _record_event(
        session,
        correlation=correlation,
        task=task,
        target=target,
        campaign=campaign,
        event_kind="node",
        node_id="research_target",
        reason_code="research_target_execution_observed",
    )
    return correlation


def observe_plan_confirmed(
    session: Session,
    *,
    campaign: Campaign,
    plan: ResearchPlan,
) -> str | None:
    """Record the deterministic pre-fan-out path after authorized confirmation."""
    graph_run_id = _campaign_graph_run_id(campaign=campaign, plan=plan)
    if graph_run_id is None:
        return None
    events = (
        ("node", "compile_plan", None, "research_plan_compiled"),
        ("transition", "await_plan_confirmation", "plan_compiled", "research_plan_compiled"),
        ("node", "await_plan_confirmation", None, "awaiting_confirmed_plan"),
        ("transition", "materialize_targets", "plan_confirmed", "confirmed_plan_hash_matches"),
        ("node", "materialize_targets", None, "materialize_targets_observed"),
    )
    for event_kind, node_id, edge_id, reason_code in events:
        _record_campaign_event(
            session,
            campaign=campaign,
            plan=plan,
            graph_run_id=graph_run_id,
            event_kind=event_kind,
            node_id=node_id,
            edge_id=edge_id,
            reason_code=reason_code,
        )
    return graph_run_id


def observe_target_reconciled(
    session: Session,
    *,
    task: AgentTask,
    target: ResearchTarget,
    campaign: Campaign,
) -> ResearchGraphCorrelation | None:
    correlation = correlate_target_task(
        session,
        task=task,
        target=target,
        campaign=campaign,
    )
    if correlation is None:
        return None
    events = (
        ("transition", "import_and_record_attempts", "target_reconciled", "target_runtime_reconciled"),
        ("node", "import_and_record_attempts", None, "import_and_record_attempts_observed"),
        ("transition", "classify_target_terminal", "attempts_recorded", "target_attempts_recorded"),
        ("node", "classify_target_terminal", None, "classify_target_terminal_observed"),
        ("transition", "shared_budget_decision", "target_classified", "target_terminal_state_classified"),
        ("node", "shared_budget_decision", None, "shared_budget_decision_observed"),
    )
    for event_kind, node_id, edge_id, reason_code in events:
        _record_event(
            session,
            correlation=correlation,
            task=task,
            target=target,
            campaign=campaign,
            event_kind=event_kind,
            node_id=node_id,
            edge_id=edge_id,
            reason_code=reason_code,
        )
    return correlation


def observe_campaign_finalized(
    session: Session,
    *,
    campaign: Campaign,
    plan: ResearchPlan,
    targets: list[ResearchTarget],
) -> str | None:
    """Record fan-in through the authoritative completed-plan materialization."""
    graph_run_id = _campaign_graph_run_id(campaign=campaign, plan=plan)
    if graph_run_id is None:
        return None
    events = (
        ("transition", "all_targets_barrier", "research_fan_in", "shared_budget_closed"),
        ("node", "all_targets_barrier", None, "all_targets_barrier_observed"),
        ("transition", "scope_assessment", "all_targets_terminal", "all_targets_covered_exhausted_or_failed"),
        ("node", "scope_assessment", None, "scope_assessment_observed"),
        ("transition", "rank_and_retain", "scope_assessed", "scope_assessment_complete"),
        ("node", "rank_and_retain", None, "rank_and_retain_observed"),
        ("transition", "research_complete", "candidates_ranked", "research_candidates_ranked_and_retained"),
        ("node", "research_complete", None, "research_complete_observed"),
    )
    target_status_counts: dict[str, int] = {}
    for target in targets:
        target_status_counts[target.status] = target_status_counts.get(target.status, 0) + 1
    aggregate = {
        "target_count": len(targets),
        "target_status_counts": dict(sorted(target_status_counts.items())),
        "retained_count": sum(target.retained_count for target in targets),
        "plan_status": plan.status,
        "campaign_status": campaign.status,
    }
    for event_kind, node_id, edge_id, reason_code in events:
        _record_campaign_event(
            session,
            campaign=campaign,
            plan=plan,
            graph_run_id=graph_run_id,
            event_kind=event_kind,
            node_id=node_id,
            edge_id=edge_id,
            reason_code=reason_code,
            aggregate=aggregate,
        )
    return graph_run_id


def _campaign_graph_run_id(*, campaign: Campaign, plan: ResearchPlan) -> str | None:
    raw_plan = _json_object(plan.raw_json)
    if (
        campaign.workspace_id is None
        or raw_plan.get("schema_version") != "1.1"
        or plan.status not in {"confirmed", "completed"}
        or not plan.confirmed_hash
        or plan.confirmed_hash != plan.content_hash
    ):
        return None
    return graph_run_id_for(
        workspace_id=campaign.workspace_id,
        campaign_id=campaign.campaign_id,
        plan_version=plan.version,
        confirmed_plan_hash=plan.confirmed_hash,
    )


def _record_campaign_event(
    session: Session,
    *,
    campaign: Campaign,
    plan: ResearchPlan,
    graph_run_id: str,
    event_kind: str,
    node_id: str,
    reason_code: str,
    edge_id: str | None = None,
    aggregate: dict[str, Any] | None = None,
) -> None:
    if campaign.workspace_id is None:
        return
    event_key = _stable_id(
        "graph-shadow-campaign-event",
        graph_run_id,
        event_kind,
        node_id,
        edge_id or "",
        reason_code,
    )
    existing = session.exec(
        select(AuditLog).where(
            AuditLog.workspace_id == campaign.workspace_id,
            AuditLog.action == f"workflow_graph_shadow_{event_kind}_observed",
            AuditLog.entity_type == "workflow_graph_shadow_event",
            AuditLog.entity_id == event_key,
        )
    ).first()
    if existing is not None:
        return
    metadata: dict[str, Any] = {
        "shadow_mode": True,
        "graph_definition_id": COORDINATED_RESEARCH_DEFINITION.definition_id,
        "graph_version": COORDINATED_RESEARCH_DEFINITION.version,
        "graph_run_id": graph_run_id,
        "node_id": node_id,
        "edge_id": edge_id,
        "reason_code": reason_code,
        "campaign_id": campaign.campaign_id,
        "campaign_row_id": campaign.id,
        "campaign_type": campaign.campaign_type,
        "research_plan_id": plan.id,
        "research_plan_version": plan.version,
        "research_plan_hash": plan.confirmed_hash,
    }
    if aggregate:
        metadata["aggregate"] = aggregate
    session.add(
        AuditLog(
            workspace_id=campaign.workspace_id,
            run_id=graph_run_id,
            actor_type="system",
            action=f"workflow_graph_shadow_{event_kind}_observed",
            entity_type="workflow_graph_shadow_event",
            entity_id=event_key,
            result_status="observed",
            reason_codes_json=json.dumps([reason_code]),
            metadata_json=json.dumps(metadata, sort_keys=True),
        )
    )


def _record_event(
    session: Session,
    *,
    correlation: ResearchGraphCorrelation,
    task: AgentTask,
    target: ResearchTarget,
    campaign: Campaign,
    event_kind: str,
    node_id: str,
    reason_code: str,
    edge_id: str | None = None,
) -> None:
    if task.workspace_id is None:
        return
    event_key = _stable_id(
        "graph-shadow-event",
        correlation.execution_key,
        event_kind,
        node_id,
        edge_id or "",
        reason_code,
    )
    existing = session.exec(
        select(AuditLog).where(
            AuditLog.workspace_id == task.workspace_id,
            AuditLog.action == f"workflow_graph_shadow_{event_kind}_observed",
            AuditLog.entity_type == "workflow_graph_shadow_event",
            AuditLog.entity_id == event_key,
        )
    ).first()
    if existing is not None:
        return
    metadata: dict[str, Any] = {
        "shadow_mode": True,
        "graph_definition_id": COORDINATED_RESEARCH_DEFINITION.definition_id,
        "graph_version": COORDINATED_RESEARCH_DEFINITION.version,
        "graph_run_id": correlation.graph_run_id,
        "execution_key": correlation.execution_key,
        "node_id": node_id,
        "edge_id": edge_id,
        "reason_code": reason_code,
        "campaign_id": campaign.campaign_id,
        "campaign_type": campaign.campaign_type,
        "campaign_row_id": campaign.id,
        "research_plan_id": correlation.plan_id,
        "research_plan_version": correlation.plan_version,
        "research_plan_hash": correlation.plan_hash,
        "research_target_id": target.id,
        "target_id": target.target_id,
        "agent_task_id": task.id,
        "task_id": task.task_id,
        "budget_phase": correlation.budget_phase,
        "logical_generation": correlation.logical_generation,
    }
    session.add(
        AuditLog(
            workspace_id=task.workspace_id,
            run_id=correlation.graph_run_id,
            actor_type="system",
            action=f"workflow_graph_shadow_{event_kind}_observed",
            entity_type="workflow_graph_shadow_event",
            entity_id=event_key,
            result_status="observed",
            reason_codes_json=json.dumps([reason_code]),
            metadata_json=json.dumps(metadata, sort_keys=True),
        )
    )


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
