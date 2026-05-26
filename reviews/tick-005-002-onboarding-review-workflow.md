# AM-005-002 Review: Onboarding Review Workflow

Status: `pending`
Date: 2026-05-15

## Scope Reviewed

- `backend/app/onboarding/promotion.py`
- `backend/app/onboarding/__init__.py`
- `backend/app/api/routes.py`
- `backend/app/schemas/api.py`
- `backend/app/imports/domain_normalizer.py`
- `backend/app/gates/evaluate_only.py`
- `backend/tests/test_onboarding_promotion.py`
- `backend/tests/test_import_domain_normalization.py`
- `backend/tests/test_evaluate_only_gate.py`
- `BACKLOG.md`
- `CHARTER.md`
- `docs/AGENT_BRIEF.md`

## Coordinator Pre-Review Notes

- Imported onboarding snapshots now start as `candidate`.
- Promotion requires explicit reviewer confirmation for profile, master CV, and policy.
- Promotion blocks review-needed provenance, duplicate master CV claim IDs, non-conservative policy defaults, and review-needed policy exclusion provenance.
- Promotion writes audit logs and supersedes previous approved snapshots.
- Evaluate-only gate blocks non-approved onboarding snapshots.
- Generated evaluate-only gate results are cleared on same-run re-import to avoid stale pass summaries attaching to fresh candidate snapshots.
- Malformed persisted send-intent JSON now produces a blocked gate result and completed audit.
- No sending, Gmail integration, OpenAI dependency, email adapter, or reservation mode was added.

## Bounded Reviewer Findings

- Fixed: stale generated evaluate-only results can no longer survive same-run re-import and attach to fresh candidate snapshots.
- Fixed: malformed persisted send-intent JSON no longer crashes gate evaluation before writing a blocked result and completed audit.

## Test Results

- `uv run --python 3.12 --extra test pytest backend/tests/test_onboarding_promotion.py` -> `8 passed`
- `uv run --python 3.12 --extra test pytest backend/tests/test_import_domain_normalization.py backend/tests/test_evaluate_only_gate.py backend/tests/test_onboarding_promotion.py` -> `59 passed`
- `uv run --python 3.12 --extra test pytest backend/tests/test_import_api.py backend/tests/test_dashboard_api.py backend/tests/test_boundaries.py backend/tests/test_dashboard_ui.py` -> `23 passed`
- `uv run --python 3.12 --extra test pytest` -> `147 passed, 1 skipped`

## Reviewer Verdict

Bounded reviewer issues addressed; external reviewer pass still pending.
