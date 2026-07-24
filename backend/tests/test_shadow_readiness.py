from __future__ import annotations

from datetime import datetime, timezone

from backend.app.workflow.graph import coordinated_research_v1
from backend.app.workflow.shadow_readiness import (
    ShadowEvidenceInputs,
    VerificationEvidence,
    evaluate_shadow_readiness,
    render_markdown,
)


FIXED_TIME = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)


def _complete_inputs(**updates) -> ShadowEvidenceInputs:
    definition = coordinated_research_v1()
    values = {
        "event_count": 200,
        "graph_run_count": 8,
        "campaign_count": 4,
        "target_count": 12,
        "execution_count": 16,
        "completed_execution_count": 16,
        "campaign_kinds": ["initiative_outreach", "listed_job_search"],
        "node_ids": sorted(node.node_id for node in definition.nodes),
        "observed_edges": sorted(
            (edge.edge_id, edge.reason_code) for edge in definition.edges
        ),
        "terminal_target_states": ["covered", "exhausted", "failed"],
        "max_targets_per_graph_run": 3,
        "shared_lease_generations": [1, 2, 3],
        "verification": VerificationEvidence(
            postgres_concurrency="passed",
            crash_recovery="passed",
            workspace_isolation_and_cancellation="passed",
        ),
    }
    values.update(updates)
    return ShadowEvidenceInputs(**values)


def test_complete_evidence_is_ready_and_markdown_is_aggregate_only():
    report = evaluate_shadow_readiness(
        _complete_inputs(),
        generated_at=FIXED_TIME,
    )

    assert report.verdict == "ready"
    assert report.gaps == []
    assert report.mismatches == []
    markdown = render_markdown(report)
    assert "Verdict: **ready**" in markdown
    assert "explicitly approved cutover tick" in markdown
    assert "campaign names" in markdown


def test_missing_branch_and_external_proofs_are_insufficient():
    definition = coordinated_research_v1()
    inputs = _complete_inputs(
        campaign_kinds=["initiative_outreach"],
        node_ids=[
            node.node_id
            for node in definition.nodes
            if node.node_id != "research_complete"
        ],
        observed_edges=[
            (edge.edge_id, edge.reason_code)
            for edge in definition.edges
            if edge.edge_id != "shared_budget_lease"
        ],
        terminal_target_states=["covered"],
        max_targets_per_graph_run=1,
        shared_lease_generations=[],
        completed_plan_missing_finalization=["plan-old"],
        verification=VerificationEvidence(),
    )

    report = evaluate_shadow_readiness(inputs, generated_at=FIXED_TIME)

    assert report.verdict == "insufficient_evidence"
    assert "missing_campaign_kind:listed_job_search" in report.gaps
    assert "missing_node:research_complete" in report.gaps
    assert (
        "missing_edge:shared_budget_lease:bounded_shared_budget_lease_allocated"
        in report.gaps
    )
    assert "missing_terminal_state:exhausted" in report.gaps
    assert "missing_terminal_state:failed" in report.gaps
    assert "missing_multi_target_fan_out" in report.gaps
    assert "missing_shared_budget_cycle" in report.gaps
    assert "missing_completed_plan_finalization:plan-old" in report.gaps
    assert "verification_unavailable:postgres_concurrency" in report.gaps


def test_any_contradiction_is_not_ready_with_stable_mismatch_ids():
    inputs = _complete_inputs(
        duplicate_event_ids=["event-1"],
        missing_execution_key_task_ids=["task-missing"],
        duplicate_execution_keys=["execution-duplicate"],
        plan_hash_mismatch_ids=["plan-mismatch"],
        invalid_node_event_ids=["event-node"],
        invalid_transition_event_ids=["event-edge"],
        incomplete_execution_keys=["execution-incomplete"],
        shared_lease_generations=[1, 4],
        verification=VerificationEvidence(
            postgres_concurrency="failed",
            crash_recovery="passed",
            workspace_isolation_and_cancellation="passed",
        ),
    )

    first = evaluate_shadow_readiness(inputs, generated_at=FIXED_TIME)
    second = evaluate_shadow_readiness(inputs, generated_at=FIXED_TIME)

    assert first.verdict == "not_ready"
    assert first.model_dump_json() == second.model_dump_json()
    assert {item.category for item in first.mismatches} == {
        "duplicate_event",
        "missing_execution_key",
        "duplicate_execution_key",
        "plan_hash_mismatch",
        "invalid_node",
        "invalid_transition",
        "incomplete_execution_trace",
        "shared_cycle_bound",
        "verification_failure",
    }
    assert all(
        item.mismatch_id.startswith("shadow-mismatch-")
        for item in first.mismatches
    )
