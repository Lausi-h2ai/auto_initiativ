# Coordinated Research Shadow Readiness

Generated: `2026-07-24T14:08:00.296851+00:00`

Verdict: **insufficient_evidence**

This report is aggregate-only. It contains no campaign names, target labels, prompts, documents, or personal profile data.

## Evidence Summary

- Events: 0
- Historical pre-contract events: 128
- Graph runs: 0
- Campaigns: 0
- Targets: 0
- Executions: 0 (0 completed)
- Mismatches: 0
- Coverage gaps: 29

## Coverage

- Campaign kinds: none
- Nodes: none
- Edges: none
- Terminal target states: none
- Maximum targets in one graph run: 0
- Shared lease generations: none

## Required Verification

- PostgreSQL concurrency: passed
- Crash recovery: passed
- Workspace isolation and cancellation: passed

These proofs passed against a disposable PostgreSQL 16 database at commit
`02c04f3`. The test set covers execution-key uniqueness, competing claims,
expired-lease reconciliation, uncertain-launch blocking, workspace isolation,
and campaign pause behavior.

## Blocking Gaps

- `missing_campaign_kind:initiative_outreach`
- `missing_campaign_kind:listed_job_search`
- `missing_edge:all_targets_terminal:all_targets_covered_exhausted_or_failed`
- `missing_edge:attempts_recorded:target_attempts_recorded`
- `missing_edge:candidates_ranked:research_candidates_ranked_and_retained`
- `missing_edge:plan_compiled:research_plan_compiled`
- `missing_edge:plan_confirmed:confirmed_plan_hash_matches`
- `missing_edge:research_fan_in:shared_budget_closed`
- `missing_edge:scope_assessed:scope_assessment_complete`
- `missing_edge:shared_budget_lease:bounded_shared_budget_lease_allocated`
- `missing_edge:target_classified:target_terminal_state_classified`
- `missing_edge:target_reconciled:target_runtime_reconciled`
- `missing_edge:targets_materialized:research_target_materialized`
- `missing_multi_target_fan_out`
- `missing_node:all_targets_barrier`
- `missing_node:await_plan_confirmation`
- `missing_node:classify_target_terminal`
- `missing_node:compile_plan`
- `missing_node:import_and_record_attempts`
- `missing_node:materialize_targets`
- `missing_node:rank_and_retain`
- `missing_node:research_complete`
- `missing_node:research_target`
- `missing_node:scope_assessment`
- `missing_node:shared_budget_decision`
- `missing_shared_budget_cycle`
- `missing_terminal_state:covered`
- `missing_terminal_state:exhausted`
- `missing_terminal_state:failed`

## Mismatches

- None

## Decision

Coordinated research remains shadow-observed. This report does not authorize cutover.
