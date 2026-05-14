# Phase 1 Review Report

Review date: 2026-05-13

## Overall Verdict

Pass with concerns.

The implementation preserves the core Phase 1 safety boundary. I found no Gmail sending code, no email adapter, no send endpoint, no OpenAI API or LLM runtime dependency, no deterministic safety gate implementation, no send reservation implementation, and no normalized domain persistence beyond operational import records.

The remaining concerns are implementation-quality issues: Pydantic helper models are more permissive than the JSON Schemas for optional fields, unexpected import failures are not handled/audited robustly, and test coverage does not yet prove Pydantic/schema alignment or crash-path audit behavior.

Verification run:

```text
uv run --python 3.12 --extra test pytest
20 passed
```

## Current-State Update

Later Phase 1 fixes addressed the implementation-quality concerns above while preserving Phase 1 scope:

- Pydantic helper models now reject explicit `null` values while still allowing omitted optional fields.
- Tests now validate all valid fixture outputs through the matching Pydantic models and include representative explicit-null parity coverage.
- `RunImportService.import_run()` now records unexpected import exceptions as `import_failed` audit events and rolls back incomplete replacement imports.
- Re-import replacement behavior is covered by tests, including preservation of prior operational rows when a replacement import crashes.
- The valid `gate_result.json` fixture no longer includes `reservation_id`.

Current verification:

```text
uv run --python 3.12 --extra test pytest
41 passed
```

The gate status naming discrepancy remains intentionally deferred for Phase 3 schema/docs reconciliation.

## Critical Findings

None.

No reviewed code violates the non-negotiable rule that agents produce files and programs make decisions. No reviewed code can send email.

## Non-Critical Findings

### 1. Pydantic models allow `null` where JSON Schemas only allow omission

Files:

- `backend/app/schemas/agent_outputs.py`
- `schemas/*.schema.json`

The JSON Schemas generally model optional properties by omitting them from `required`, but they do not include `"null"` in the property type. The Pydantic models use `| None = None` for many of those same properties, which accepts explicit JSON `null`.

Examples:

- `CompanyCandidate.website_url`, `description`, `industry_tags`, `locations`, `remote_policy`, `potential_policy_conflicts`
- `ContactCandidate.name`, `role_title`, `profile_url`
- `EmailDraft.body_html`, `tone`, `attachments`
- `GateResult.reservation_id`, `policy_snapshot_id`
- `PolicyOutreach.require_manual_review_before_send`
- `SendIntent.recipient_name`, `company_domain`, `body_html`, `claim_refs`
- multiple optional `UserProfile` and `MasterCvProfile` fields

Current imports use JSON Schema validation as the authority, so this is not currently a send-safety issue. It is still a Phase 1 alignment concern because the Pydantic models are intended to match the schema contracts and may later be used at API/import boundaries.

Suggested fix:

- Add tests that feed explicit `null` values into each optional schema field and assert both JSON Schema validation and Pydantic validation reject them.
- Update Pydantic models to distinguish "field absent" from "field present with null", using validators or another strict pattern.
- Keep JSON Schema validation as the import authority.

### 2. Import service lacks a top-level failure path for unexpected errors

Files:

- `backend/app/imports/import_service.py`
- `backend/app/imports/validation.py`

`RunImportService.import_run()` handles known validation failures and missing output directories, but it does not wrap the import lifecycle in a top-level `try` / `except`. Unexpected failures during schema loading, validation, hashing, file stat calls, database writes, or audit serialization can leave the run in an incomplete state and may not persist an `import_failed` audit event.

The Phase 1 task breakdown explicitly calls for import failure handling and audit logging for import failure. The current implementation handles the missing-directory case, but not general import crashes.

Suggested fix:

- Wrap the import lifecycle after run creation in deterministic error handling.
- On unexpected exception, roll back partial writes as needed, mark the run `import_failed`, and write an `import_failed` audit event with a machine-readable reason such as `import_exception`.
- Add tests with a stub validator or broken schema path to prove that unexpected failures result in a persisted failed run and audit event.

### 3. Re-import behavior deletes previous operational rows before confirming the new import can complete

File:

- `backend/app/imports/import_service.py`

`_clear_previous_import_rows()` runs before file validation. If an unexpected exception happens after that point, the previous imported file and validation rows for the run can be lost while the replacement import is incomplete.

This is not out of scope, and the current idempotent-replacement choice is acceptable for Phase 1 if it is intentional. The risk is observability loss on failed re-imports.

Suggested fix:

- Either keep replacement semantics but make the operation transactional and crash-audited, or introduce explicit import-attempt records later.
- Add a test that simulates failure after previous rows are cleared and verifies the chosen behavior.

### 4. Pydantic/schema alignment is not directly tested

Files:

- `backend/app/schemas/agent_outputs.py`
- `backend/tests/test_schema_validation.py`

Tests cover JSON Schema validation well for representative cases, but they do not validate all fixture outputs through `AGENT_OUTPUT_MODELS`, and they do not compare JSON Schema acceptance/rejection with Pydantic acceptance/rejection.

Suggested fix:

- Add a parametrized test over all known schema filenames.
- Validate each valid fixture with both JSON Schema and the matching Pydantic model.
- Add representative invalid fixtures for null optional fields, bad dates, bad URLs, bad emails, invalid enums, extra properties, and confidence bounds.

### 5. The valid `gate_result.json` fixture includes a reservation ID

File:

- `backend/tests/fixtures/valid_run/output/gate_result.json`

The fixture is schema-valid and the backend only imports it as raw operational data, so this is not a functional Phase 1 violation. However, `reservation_id: "reservation-1"` can be confusing in Phase 1 because send reservations are explicitly out of scope.

Suggested fix:

- Prefer omitting `reservation_id` from the Phase 1 valid fixture unless the test is explicitly documenting schema-only import of future-looking fields.
- If retained, add a short test or fixture comment in future documentation explaining that Phase 1 validates imported files only and does not create or trust reservations.

### 6. Gate status naming discrepancy remains intentionally unresolved

Files:

- `docs/SAFETY_GATES.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `schemas/gate_result.schema.json`
- `backend/app/schemas/agent_outputs.py`

The safety docs say allowed gate statuses are `passed_evaluate_only`, `blocked`, `needs_review`, and `reserved_for_send`, and that `sent` / `send_failed` are not gate statuses. The current JSON Schema accepts `passed_dry_run`, `reserved`, `sent`, and `send_failed`; the Pydantic model mirrors the schema.

This discrepancy was already called out as a Phase 1 risk in `docs/PHASE_1_TASK_BREAKDOWN.md`. The implementation correctly treats JSON Schema as the Phase 1 import authority and does not produce or execute gate results. This should be reconciled before implementing Phase 3.

Suggested fix:

- Do not change Phase 1 behavior solely for this issue.
- Before Phase 3, reconcile the schema and docs and migrate tests/fixtures to the chosen status names.

## Suggested Fixes

1. Add strict Pydantic/schema parity tests, especially for explicit `null` values in optional fields.
2. Tighten Pydantic models so optional schema fields may be omitted but not set to `null`.
3. Add top-level import error handling that persists `import_failed` runs and audit logs for unexpected exceptions.
4. Make re-import replacement transactional or move to explicit import-attempt records.
5. Add tests for import crash paths and file read/hash/stat failures.
6. Consider removing `reservation_id` from the Phase 1 valid gate-result fixture to reduce confusion.
7. Reconcile gate result status names before Phase 3 gate implementation.

## Acceptance Checklist Status

| Item | Status | Notes |
| --- | --- | --- |
| FastAPI app starts | Pass | `create_app()` exists; API tests instantiate the app. |
| `DRY_RUN` defaults to `true` | Pass | `Settings.dry_run` defaults to `True`; health test covers it. |
| All nine JSON schemas are loaded from `schemas/` | Pass | Registry loads all mapped schemas; test covers count and send intent presence. |
| Pydantic models are aligned with current schema contracts | Concern | Models broadly mirror schemas but accept explicit `null` where schemas reject it. |
| Import service reads `runs/<run_id>/output/` | Pass | Default path uses `RUNS_ROOT / run_id / "output"`. |
| Valid JSON outputs are accepted and persisted as operational import records | Pass | Valid run test persists 9 imported files and 9 validation results. |
| Invalid outputs are rejected with clear machine-readable errors | Pass | Tests cover malformed JSON, schema mismatch, missing expected file, and unknown JSON file. |
| Runs, imported files, validation results, and audit logs are persisted | Pass | Only these four tables are defined and tested. |
| API endpoints expose imported runs, imported files, validation results, and audit logs | Pass | API tests cover health, import, runs, files, validation results, and audit logs. |
| No normalized domain persistence is implemented | Pass | No company/contact/draft/profile/policy/send-intent/gate-result tables exist. |
| No dedupe logic or send reservations are implemented | Pass | No dedupe service, reservation table, or reservation flow exists. |
| No email adapter, Gmail sending, or send endpoint exists | Pass | Boundary tests and source review confirm this. |
| No OpenAI API dependency is added | Pass | `pyproject.toml` has no OpenAI dependency; boundary test covers declared dependencies. |
| Tests cover valid and invalid imports | Pass with concern | Core cases are covered; crash-path and Pydantic/schema parity tests are missing. |
| Existing docs and schemas remain unchanged unless separately authorized | Pass | This review only adds this report. |

## Files Inspected

Repository instructions and docs:

- `AGENTS.md`
- `README.md`
- `docs/ARCHITECTURE.md`
- `docs/IMPLEMENTATION_PLAN.md`
- `docs/AGENT_BOUNDARIES.md`
- `docs/SAFETY_GATES.md`
- `docs/DATA_MODEL.md`
- `docs/CODEX_WORKFLOW.md`
- `docs/SEND_INTENT_SPEC.md`
- `docs/PHASE_1_TASK_BREAKDOWN.md`
- `docs/PRODUCT_SPEC.md`
- `docs/ONBOARDING_SPEC.md`

Schemas:

- `schemas/company_candidate.schema.json`
- `schemas/contact_candidate.schema.json`
- `schemas/email_draft.schema.json`
- `schemas/fit_evaluation.schema.json`
- `schemas/gate_result.schema.json`
- `schemas/master_cv_profile.schema.json`
- `schemas/policy.schema.json`
- `schemas/send_intent.schema.json`
- `schemas/user_profile.schema.json`

Backend implementation:

- `backend/app/__init__.py`
- `backend/app/main.py`
- `backend/app/api/__init__.py`
- `backend/app/api/routes.py`
- `backend/app/core/__init__.py`
- `backend/app/core/config.py`
- `backend/app/db/__init__.py`
- `backend/app/db/models.py`
- `backend/app/db/session.py`
- `backend/app/imports/__init__.py`
- `backend/app/imports/file_classifier.py`
- `backend/app/imports/import_service.py`
- `backend/app/imports/schema_registry.py`
- `backend/app/imports/validation.py`
- `backend/app/schemas/__init__.py`
- `backend/app/schemas/api.py`
- `backend/app/schemas/agent_outputs.py`

Tests and fixtures:

- `backend/tests/conftest.py`
- `backend/tests/test_boundaries.py`
- `backend/tests/test_import_api.py`
- `backend/tests/test_import_service.py`
- `backend/tests/test_schema_validation.py`
- `backend/tests/fixtures/valid_run/output/company_candidate.json`
- `backend/tests/fixtures/valid_run/output/contact_candidate.json`
- `backend/tests/fixtures/valid_run/output/email_draft.json`
- `backend/tests/fixtures/valid_run/output/fit_evaluation.json`
- `backend/tests/fixtures/valid_run/output/gate_result.json`
- `backend/tests/fixtures/valid_run/output/master_cv_profile.json`
- `backend/tests/fixtures/valid_run/output/policy.json`
- `backend/tests/fixtures/valid_run/output/send_intent.json`
- `backend/tests/fixtures/valid_run/output/user_profile.json`

Packaging:

- `pyproject.toml`
