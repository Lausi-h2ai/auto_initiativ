from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlmodel import Session, select

from backend.app.core.config import get_settings
from backend.app.db.models import (
    AgentTask,
    AuditLog,
    Campaign,
    ResearchPlan,
    ResearchTarget,
)
from backend.app.db.session import build_engine
from backend.app.workflow.graph import coordinated_research_v1
from backend.app.workflow.research_graph import (
    SHADOW_INSTRUMENTATION_VERSION,
    graph_run_id_for,
)


EvidenceStatus = Literal["passed", "failed", "unavailable"]
ReadinessVerdict = Literal["ready", "not_ready", "insufficient_evidence"]

REQUIRED_CAMPAIGN_KINDS = ("initiative_outreach", "listed_job_search")
REQUIRED_TERMINAL_STATES = ("covered", "exhausted", "failed")
MAX_SHARED_LEASE_GENERATION = 3
TARGET_TRACE_REASONS = frozenset(
    {
        "research_target_execution_observed",
        "target_runtime_reconciled",
        "import_and_record_attempts_observed",
        "target_attempts_recorded",
        "classify_target_terminal_observed",
        "target_terminal_state_classified",
        "shared_budget_decision_observed",
    }
)


class VerificationEvidence(BaseModel):
    postgres_concurrency: EvidenceStatus = "unavailable"
    crash_recovery: EvidenceStatus = "unavailable"
    workspace_isolation_and_cancellation: EvidenceStatus = "unavailable"


class ShadowEvidenceInputs(BaseModel):
    event_count: int = 0
    historical_event_count: int = 0
    graph_run_count: int = 0
    campaign_count: int = 0
    target_count: int = 0
    execution_count: int = 0
    completed_execution_count: int = 0
    campaign_kinds: list[str] = Field(default_factory=list)
    node_ids: list[str] = Field(default_factory=list)
    observed_edges: list[tuple[str, str]] = Field(default_factory=list)
    terminal_target_states: list[str] = Field(default_factory=list)
    max_targets_per_graph_run: int = 0
    shared_lease_generations: list[int] = Field(default_factory=list)
    duplicate_event_ids: list[str] = Field(default_factory=list)
    missing_execution_key_task_ids: list[str] = Field(default_factory=list)
    duplicate_execution_keys: list[str] = Field(default_factory=list)
    plan_hash_mismatch_ids: list[str] = Field(default_factory=list)
    invalid_node_event_ids: list[str] = Field(default_factory=list)
    invalid_transition_event_ids: list[str] = Field(default_factory=list)
    incomplete_execution_keys: list[str] = Field(default_factory=list)
    completed_plan_missing_finalization: list[str] = Field(default_factory=list)
    verification: VerificationEvidence = Field(default_factory=VerificationEvidence)


class ReadinessMismatch(BaseModel):
    mismatch_id: str
    category: str
    reference: str
    detail: str


class ShadowCoverage(BaseModel):
    campaign_kinds: list[str] = Field(default_factory=list)
    nodes: list[str] = Field(default_factory=list)
    edges: list[str] = Field(default_factory=list)
    terminal_target_states: list[str] = Field(default_factory=list)
    max_targets_per_graph_run: int = 0
    shared_lease_generations: list[int] = Field(default_factory=list)


class ShadowReadinessReport(BaseModel):
    schema_version: Literal["1.0"] = "1.0"
    generated_at: datetime
    definition_id: Literal["coordinated_research"] = "coordinated_research"
    graph_version: Literal[1] = 1
    shadow_instrumentation_version: Literal[1] = SHADOW_INSTRUMENTATION_VERSION
    verdict: ReadinessVerdict
    summary: dict[str, int]
    coverage: ShadowCoverage
    verification: VerificationEvidence
    gaps: list[str]
    mismatches: list[ReadinessMismatch]


def _json_object(value: str | None) -> dict[str, Any]:
    try:
        parsed = json.loads(value or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _mismatch(category: str, reference: str, detail: str) -> ReadinessMismatch:
    stable = hashlib.sha256(
        f"{category}\0{reference}\0{detail}".encode("utf-8")
    ).hexdigest()[:20]
    return ReadinessMismatch(
        mismatch_id=f"shadow-mismatch-{stable}",
        category=category,
        reference=reference,
        detail=detail,
    )


def _opaque_reference(prefix: str, value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}-{digest}"


def collect_shadow_evidence(
    session: Session,
    *,
    verification: VerificationEvidence | None = None,
) -> ShadowEvidenceInputs:
    definition = coordinated_research_v1()
    valid_nodes = {node.node_id for node in definition.nodes}
    edge_contract = {
        edge.edge_id: edge.reason_code
        for edge in definition.edges
    }
    all_events = session.exec(
        select(AuditLog)
        .where(AuditLog.entity_type == "workflow_graph_shadow_event")
        .order_by(AuditLog.created_at, AuditLog.id)
    ).all()
    all_metadata_rows = [
        (event, _json_object(event.metadata_json))
        for event in all_events
    ]
    metadata_rows = [
        (event, metadata)
        for event, metadata in all_metadata_rows
        if metadata.get("shadow_instrumentation_version")
        == SHADOW_INSTRUMENTATION_VERSION
    ]
    events = [event for event, _ in metadata_rows]

    event_ids = Counter(event.entity_id or "" for event in events)
    duplicate_event_ids = sorted(
        event_id for event_id, count in event_ids.items() if event_id and count > 1
    )
    graph_run_ids = {
        str(metadata["graph_run_id"])
        for _, metadata in metadata_rows
        if metadata.get("graph_run_id")
    }
    campaign_public_ids = {
        str(metadata["campaign_id"])
        for _, metadata in metadata_rows
        if metadata.get("campaign_id")
    }
    campaigns = session.exec(
        select(Campaign).where(Campaign.campaign_id.in_(campaign_public_ids))
    ).all() if campaign_public_ids else []
    campaign_by_public_id = {campaign.campaign_id: campaign for campaign in campaigns}

    campaign_kinds: set[str] = set()
    node_ids: set[str] = set()
    observed_edges: set[tuple[str, str]] = set()
    invalid_node_event_ids: list[str] = []
    invalid_transition_event_ids: list[str] = []
    targets_by_run: dict[str, set[str]] = defaultdict(set)
    reasons_by_execution: dict[str, set[str]] = defaultdict(set)
    finalization_runs: set[str] = set()
    shared_generations: list[int] = []

    for event, metadata in metadata_rows:
        campaign_kind = metadata.get("campaign_type")
        if not campaign_kind:
            campaign = campaign_by_public_id.get(str(metadata.get("campaign_id") or ""))
            campaign_kind = campaign.campaign_type if campaign else None
        if campaign_kind:
            campaign_kinds.add(str(campaign_kind))
        node_id = str(metadata.get("node_id") or "")
        if node_id:
            node_ids.add(node_id)
            if node_id not in valid_nodes:
                invalid_node_event_ids.append(event.entity_id or f"audit-{event.id}")
        edge_id = metadata.get("edge_id")
        reason_code = str(metadata.get("reason_code") or "")
        if edge_id:
            edge_pair = (str(edge_id), reason_code)
            observed_edges.add(edge_pair)
            if edge_contract.get(str(edge_id)) != reason_code:
                invalid_transition_event_ids.append(event.entity_id or f"audit-{event.id}")
        graph_run_id = str(metadata.get("graph_run_id") or "")
        target_id = metadata.get("target_id")
        if graph_run_id and target_id:
            targets_by_run[graph_run_id].add(str(target_id))
        execution_key = metadata.get("execution_key")
        if execution_key and reason_code:
            reasons_by_execution[str(execution_key)].add(reason_code)
        if metadata.get("budget_phase") == "shared":
            try:
                shared_generations.append(int(metadata.get("logical_generation")))
            except (TypeError, ValueError):
                invalid_transition_event_ids.append(event.entity_id or f"audit-{event.id}")
        if node_id == "research_complete" and graph_run_id:
            finalization_runs.add(graph_run_id)

    tasks = (
        session.exec(
            select(AgentTask).where(
                AgentTask.graph_definition_id == definition.definition_id,
                AgentTask.graph_version == definition.version,
                AgentTask.graph_run_id.in_(graph_run_ids),
            )
        ).all()
        if graph_run_ids
        else []
    )
    missing_execution_key_task_ids = sorted(
        task.task_id for task in tasks if not task.execution_key
    )
    execution_key_counts = Counter(
        task.execution_key for task in tasks if task.execution_key
    )
    duplicate_execution_keys = sorted(
        key for key, count in execution_key_counts.items() if key and count > 1
    )
    incomplete_execution_keys = sorted(
        task.execution_key
        for task in tasks
        if task.status == "completed"
        and task.execution_key
        and not TARGET_TRACE_REASONS.issubset(
            reasons_by_execution.get(task.execution_key, set())
        )
    )

    plan_ids = {
        int(metadata["research_plan_id"])
        for _, metadata in metadata_rows
        if isinstance(metadata.get("research_plan_id"), int)
    }
    plans = session.exec(
        select(ResearchPlan).where(ResearchPlan.id.in_(plan_ids))
    ).all() if plan_ids else []
    plan_hash_mismatch_ids = sorted(
        plan.plan_id
        for plan in plans
        if not plan.confirmed_hash or plan.confirmed_hash != plan.content_hash
    )
    completed_plan_missing_finalization: list[str] = []
    for plan in plans:
        if plan.status != "completed":
            continue
        campaign = session.get(Campaign, plan.campaign_id)
        if campaign is None or campaign.workspace_id is None or not plan.confirmed_hash:
            continue
        run_id = graph_run_id_for(
            workspace_id=campaign.workspace_id,
            campaign_id=campaign.campaign_id,
            plan_version=plan.version,
            confirmed_plan_hash=plan.confirmed_hash,
        )
        if run_id not in finalization_runs:
            completed_plan_missing_finalization.append(
                _opaque_reference("plan", plan.plan_id)
            )

    targets = session.exec(
        select(ResearchTarget).where(ResearchTarget.research_plan_id.in_(plan_ids))
    ).all() if plan_ids else []
    target_ids = {
        str(metadata["target_id"])
        for _, metadata in metadata_rows
        if metadata.get("target_id")
    }
    terminal_states = {
        target.status
        for target in targets
        if target.target_id in target_ids
        and target.status in REQUIRED_TERMINAL_STATES
    }

    return ShadowEvidenceInputs(
        event_count=len(events),
        historical_event_count=len(all_events) - len(events),
        graph_run_count=len(graph_run_ids),
        campaign_count=len(campaign_public_ids),
        target_count=len(target_ids),
        execution_count=len(tasks),
        completed_execution_count=sum(task.status == "completed" for task in tasks),
        campaign_kinds=sorted(campaign_kinds),
        node_ids=sorted(node_ids),
        observed_edges=sorted(observed_edges),
        terminal_target_states=sorted(terminal_states),
        max_targets_per_graph_run=max(
            (len(targets) for targets in targets_by_run.values()),
            default=0,
        ),
        shared_lease_generations=sorted(set(shared_generations)),
        duplicate_event_ids=duplicate_event_ids,
        missing_execution_key_task_ids=missing_execution_key_task_ids,
        duplicate_execution_keys=duplicate_execution_keys,
        plan_hash_mismatch_ids=plan_hash_mismatch_ids,
        invalid_node_event_ids=sorted(set(invalid_node_event_ids)),
        invalid_transition_event_ids=sorted(set(invalid_transition_event_ids)),
        incomplete_execution_keys=incomplete_execution_keys,
        completed_plan_missing_finalization=sorted(
            completed_plan_missing_finalization
        ),
        verification=verification or VerificationEvidence(),
    )


def evaluate_shadow_readiness(
    inputs: ShadowEvidenceInputs,
    *,
    generated_at: datetime | None = None,
) -> ShadowReadinessReport:
    definition = coordinated_research_v1()
    required_nodes = {node.node_id for node in definition.nodes}
    required_edges = {(edge.edge_id, edge.reason_code) for edge in definition.edges}
    observed_nodes = set(inputs.node_ids)
    observed_edges = set(inputs.observed_edges)
    terminal_states = set(inputs.terminal_target_states)
    campaign_kinds = set(inputs.campaign_kinds)
    mismatches: list[ReadinessMismatch] = []

    mismatch_groups = (
        ("duplicate_event", inputs.duplicate_event_ids, "Shadow event ID was recorded more than once."),
        ("missing_execution_key", inputs.missing_execution_key_task_ids, "Correlated task has no stable execution key."),
        ("duplicate_execution_key", inputs.duplicate_execution_keys, "Stable execution key is reused by multiple tasks."),
        ("plan_hash_mismatch", inputs.plan_hash_mismatch_ids, "Confirmed plan hash does not match the persisted content hash."),
        ("invalid_node", inputs.invalid_node_event_ids, "Observed event names a node outside coordinated_research v1."),
        ("invalid_transition", inputs.invalid_transition_event_ids, "Observed edge and reason code do not match coordinated_research v1."),
        ("incomplete_execution_trace", inputs.incomplete_execution_keys, "Completed target execution is missing mandatory shadow events."),
    )
    for category, references, detail in mismatch_groups:
        mismatches.extend(
            _mismatch(category, reference, detail)
            for reference in sorted(references)
        )
    for generation in inputs.shared_lease_generations:
        if generation < 1 or generation > MAX_SHARED_LEASE_GENERATION:
            mismatches.append(
                _mismatch(
                    "shared_cycle_bound",
                    str(generation),
                    "Shared-budget generation is outside the declared cycle bound.",
                )
            )
    for name, status in inputs.verification.model_dump().items():
        if status == "failed":
            mismatches.append(
                _mismatch(
                    "verification_failure",
                    name,
                    f"Required {name.replace('_', ' ')} verification failed.",
                )
            )

    gaps: list[str] = []
    for kind in sorted(set(REQUIRED_CAMPAIGN_KINDS) - campaign_kinds):
        gaps.append(f"missing_campaign_kind:{kind}")
    for node_id in sorted(required_nodes - observed_nodes):
        gaps.append(f"missing_node:{node_id}")
    for edge_id, reason_code in sorted(required_edges - observed_edges):
        gaps.append(f"missing_edge:{edge_id}:{reason_code}")
    for status in sorted(set(REQUIRED_TERMINAL_STATES) - terminal_states):
        gaps.append(f"missing_terminal_state:{status}")
    if inputs.max_targets_per_graph_run < 2:
        gaps.append("missing_multi_target_fan_out")
    if not inputs.shared_lease_generations:
        gaps.append("missing_shared_budget_cycle")
    for plan_id in sorted(inputs.completed_plan_missing_finalization):
        gaps.append(f"missing_completed_plan_finalization:{plan_id}")
    for name, status in inputs.verification.model_dump().items():
        if status == "unavailable":
            gaps.append(f"verification_unavailable:{name}")

    mismatches.sort(key=lambda item: item.mismatch_id)
    gaps.sort()
    verdict: ReadinessVerdict
    if mismatches:
        verdict = "not_ready"
    elif gaps:
        verdict = "insufficient_evidence"
    else:
        verdict = "ready"
    return ShadowReadinessReport(
        generated_at=generated_at or datetime.now(timezone.utc),
        verdict=verdict,
        summary={
            "events": inputs.event_count,
            "historical_events": inputs.historical_event_count,
            "graph_runs": inputs.graph_run_count,
            "campaigns": inputs.campaign_count,
            "targets": inputs.target_count,
            "executions": inputs.execution_count,
            "completed_executions": inputs.completed_execution_count,
            "mismatches": len(mismatches),
            "gaps": len(gaps),
        },
        coverage=ShadowCoverage(
            campaign_kinds=sorted(inputs.campaign_kinds),
            nodes=sorted(inputs.node_ids),
            edges=sorted(edge_id for edge_id, _ in inputs.observed_edges),
            terminal_target_states=sorted(inputs.terminal_target_states),
            max_targets_per_graph_run=inputs.max_targets_per_graph_run,
            shared_lease_generations=sorted(inputs.shared_lease_generations),
        ),
        verification=inputs.verification,
        gaps=gaps,
        mismatches=mismatches,
    )


def render_markdown(report: ShadowReadinessReport) -> str:
    summary = report.summary
    lines = [
        "# Coordinated Research Shadow Readiness",
        "",
        f"Generated: `{report.generated_at.isoformat()}`",
        "",
        f"Verdict: **{report.verdict}**",
        "",
        "This report is aggregate-only. It contains no campaign names, target labels, prompts, documents, or personal profile data.",
        "",
        "## Evidence Summary",
        "",
        f"- Events: {summary['events']}",
        f"- Historical pre-contract events: {summary['historical_events']}",
        f"- Graph runs: {summary['graph_runs']}",
        f"- Campaigns: {summary['campaigns']}",
        f"- Targets: {summary['targets']}",
        f"- Executions: {summary['executions']} ({summary['completed_executions']} completed)",
        f"- Mismatches: {summary['mismatches']}",
        f"- Coverage gaps: {summary['gaps']}",
        "",
        "## Coverage",
        "",
        f"- Campaign kinds: {', '.join(report.coverage.campaign_kinds) or 'none'}",
        f"- Nodes: {', '.join(report.coverage.nodes) or 'none'}",
        f"- Edges: {', '.join(report.coverage.edges) or 'none'}",
        f"- Terminal target states: {', '.join(report.coverage.terminal_target_states) or 'none'}",
        f"- Maximum targets in one graph run: {report.coverage.max_targets_per_graph_run}",
        f"- Shared lease generations: {', '.join(map(str, report.coverage.shared_lease_generations)) or 'none'}",
        "",
        "## Required Verification",
        "",
        f"- PostgreSQL concurrency: {report.verification.postgres_concurrency}",
        f"- Crash recovery: {report.verification.crash_recovery}",
        f"- Workspace isolation and cancellation: {report.verification.workspace_isolation_and_cancellation}",
        "",
        "## Blocking Gaps",
        "",
    ]
    lines.extend(f"- `{gap}`" for gap in report.gaps)
    if not report.gaps:
        lines.append("- None")
    lines.extend(["", "## Mismatches", ""])
    lines.extend(
        f"- `{item.mismatch_id}` — {item.category} (`{item.reference}`): {item.detail}"
        for item in report.mismatches
    )
    if not report.mismatches:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Decision",
            "",
            (
                "Coordinated research is ready for a separate, explicitly approved cutover tick."
                if report.verdict == "ready"
                else "Coordinated research remains shadow-observed. This report does not authorize cutover."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate coordinated-research shadow cutover readiness."
    )
    parser.add_argument("--database-url", default=get_settings().database_url)
    parser.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
    )
    for flag in (
        "postgres-concurrency",
        "crash-recovery",
        "workspace-isolation-and-cancellation",
    ):
        parser.add_argument(
            f"--{flag}",
            choices=("passed", "failed", "unavailable"),
            default="unavailable",
        )
    return parser


def main() -> None:
    args = _parser().parse_args()
    verification = VerificationEvidence(
        postgres_concurrency=args.postgres_concurrency,
        crash_recovery=args.crash_recovery,
        workspace_isolation_and_cancellation=args.workspace_isolation_and_cancellation,
    )
    with Session(build_engine(args.database_url)) as session:
        inputs = collect_shadow_evidence(session, verification=verification)
    report = evaluate_shadow_readiness(inputs)
    if args.format == "markdown":
        print(render_markdown(report), end="")
    else:
        print(report.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
