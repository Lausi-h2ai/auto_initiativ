# Coordinated Research Shadow Readiness

Generated: `2026-07-24T13:48:59.488910+00:00`

Verdict: **insufficient_evidence**

This report is aggregate-only. It contains no campaign names, target labels, prompts, documents, or personal profile data.

## Evidence Summary

- Events: 128
- Graph runs: 6
- Campaigns: 2
- Targets: 4
- Executions: 16 (16 completed)
- Mismatches: 0
- Coverage gaps: 25

## Coverage

- Campaign kinds: listed_job_search
- Nodes: classify_target_terminal, import_and_record_attempts, research_target, shared_budget_decision
- Edges: attempts_recorded, target_classified, target_reconciled, targets_materialized
- Terminal target states: covered, exhausted, failed
- Maximum targets in one graph run: 3
- Shared lease generations: none

## Required Verification

- PostgreSQL concurrency: unavailable
- Crash recovery: unavailable
- Workspace isolation and cancellation: unavailable

## Blocking Gaps

- `missing_campaign_kind:initiative_outreach`
- `missing_completed_plan_finalization:plan-4ea9d00cb0bd`
- `missing_completed_plan_finalization:plan-5dc5ce0f9f05`
- `missing_completed_plan_finalization:plan-67d44ca4758c`
- `missing_completed_plan_finalization:plan-a6ffd4bd3e84`
- `missing_completed_plan_finalization:plan-ce0156a502cf`
- `missing_completed_plan_finalization:plan-e6e50d176f2f`
- `missing_edge:all_targets_terminal:all_targets_covered_exhausted_or_failed`
- `missing_edge:candidates_ranked:research_candidates_ranked_and_retained`
- `missing_edge:plan_compiled:research_plan_compiled`
- `missing_edge:plan_confirmed:confirmed_plan_hash_matches`
- `missing_edge:research_fan_in:shared_budget_closed`
- `missing_edge:scope_assessed:scope_assessment_complete`
- `missing_edge:shared_budget_lease:bounded_shared_budget_lease_allocated`
- `missing_node:all_targets_barrier`
- `missing_node:await_plan_confirmation`
- `missing_node:compile_plan`
- `missing_node:materialize_targets`
- `missing_node:rank_and_retain`
- `missing_node:research_complete`
- `missing_node:scope_assessment`
- `missing_shared_budget_cycle`
- `verification_unavailable:crash_recovery`
- `verification_unavailable:postgres_concurrency`
- `verification_unavailable:workspace_isolation_and_cancellation`

## Mismatches

- None

## Decision

Coordinated research remains shadow-observed. This report does not authorize cutover.
