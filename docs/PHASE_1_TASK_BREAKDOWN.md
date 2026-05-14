# Phase 1 Task Breakdown

## 1. Phase 1 Objective

Create a dry-run FastAPI backend skeleton that can import Codex run output files, validate each JSON file against the existing schemas in `schemas/`, persist only operational import records, and expose API endpoints for inspecting runs, imported files, validation results, and audit events.

Phase 1 must keep the core safety boundary intact: agents produce files, the backend validates and records them, and no component sends email.

## 2. Explicit In-Scope Items

- Minimal FastAPI application with health and import inspection endpoints.
- Configuration object with `DRY_RUN=true` as the default.
- Database setup using SQLModel or SQLAlchemy.
- Durable persistence models only for:
  - `Run`
  - `ImportedFile`
  - `ValidationResult`
  - `AuditLog`
- Pydantic models aligned with all current JSON schemas:
  - `company_candidate.schema.json`
  - `contact_candidate.schema.json`
  - `email_draft.schema.json`
  - `fit_evaluation.schema.json`
  - `gate_result.schema.json`
  - `master_cv_profile.schema.json`
  - `policy.schema.json`
  - `send_intent.schema.json`
  - `user_profile.schema.json`
- JSON Schema validation service for imported files.
- Run output import service that reads `runs/<run_id>/output/`.
- File classification that maps known output filenames to schema files.
- Clear validation errors for invalid JSON, unknown file type, schema mismatch, and missing run output directory.
- Audit logging for import start, per-file validation success or failure, import completion, and import failure.
- API endpoints to inspect imported runs and validation results.
- Tests for valid and invalid imports.
- No normalized domain persistence beyond raw imported file metadata and validation records.

## 3. Explicit Out-of-Scope Items

- Gmail sending or any other email adapter.
- OpenAI API dependency or LLM calls.
- Safety gate implementation beyond schema validation and operational logging.
- `reserve_for_send` behavior, send reservations, sent message records, or adapter handoff.
- Full normalized persistence for companies, contacts, evaluations, drafts, profiles, policies, send intents, or gate results.
- Phase 2 dedupe/domain models, unique outreach constraints, company policy keys, or recipient dedupe logic.
- Full frontend or dashboard UI.
- Codex run orchestration that creates run folders, task files, or agent instructions.
- Profile onboarding, CV tailoring logic, source resolution, attachment existence checks, claim ledger validation, and policy enforcement.
- Modifying existing architecture decisions or existing documentation except if a later task explicitly requests reconciliation.

## 4. Proposed File Structure

Use a small backend package and keep the repository-level JSON schemas as the contract source of truth.

```text
backend/
  app/
    __init__.py
    main.py
    api/
      __init__.py
      routes.py
    core/
      __init__.py
      config.py
    db/
      __init__.py
      models.py
      session.py
    imports/
      __init__.py
      file_classifier.py
      import_service.py
      schema_registry.py
      validation.py
    schemas/
      __init__.py
      api.py
      agent_outputs.py
  tests/
    conftest.py
    fixtures/
      valid_run/
        output/
      invalid_run/
        output/
    test_import_service.py
    test_import_api.py
    test_schema_validation.py
pyproject.toml
```

Recommended module responsibilities:

- `main.py`: create FastAPI app and include routes.
- `core/config.py`: define settings, including `DRY_RUN=true`, `DATABASE_URL`, `RUNS_ROOT`, and `SCHEMAS_ROOT`.
- `db/models.py`: define only `Run`, `ImportedFile`, `ValidationResult`, and `AuditLog`.
- `imports/schema_registry.py`: load schema files from `schemas/` and expose known schema mappings.
- `imports/file_classifier.py`: map filenames to schema names.
- `imports/validation.py`: parse JSON and validate against JSON Schema.
- `imports/import_service.py`: coordinate run import, persistence, status updates, and audit events.
- `schemas/agent_outputs.py`: Pydantic models aligned with current schemas for typed API/import boundaries.
- `schemas/api.py`: API response models for runs, imported files, validation results, and audit events.

## 5. Implementation Tasks in Recommended Order

1. Add project packaging and test tooling.
   - Add `pyproject.toml`.
   - Include FastAPI, Uvicorn, Pydantic, SQLModel or SQLAlchemy, a Postgres driver, `jsonschema`, pytest, and HTTP test client dependencies.
   - Keep dependency list minimal.

2. Add application configuration.
   - Create `backend/app/core/config.py`.
   - Default `DRY_RUN` to `true`.
   - Add `DATABASE_URL`, `RUNS_ROOT`, and `SCHEMAS_ROOT`.
   - Make settings injectable or overrideable in tests.

3. Add minimal database models.
   - Create `Run` with fields such as `id`, `run_id`, `agent_type`, `output_path`, `status`, `started_at`, `completed_at`, `created_at`, and `updated_at`.
   - Create `ImportedFile` with fields such as `id`, `run_id`, `path`, `filename`, `schema_name`, `sha256`, `size_bytes`, `status`, `imported_at`, and optional raw JSON storage.
   - Create `ValidationResult` with fields such as `id`, `imported_file_id`, `status`, `schema_name`, `error_count`, `errors_json`, and `validated_at`.
   - Create `AuditLog` with fields such as `id`, `actor_type`, `action`, `entity_type`, `entity_id`, `result_status`, `reason_codes_json`, `metadata_json`, and `created_at`.
   - Do not add company, contact, draft, profile, policy, send intent, gate result, reservation, or sent message tables.

4. Add database session and initialization.
   - Use SQLModel or SQLAlchemy consistently.
   - Support Postgres through `DATABASE_URL`.
   - Tests may override with an isolated test database or SQLite in-memory database if the implementation avoids SQLite-specific behavior.
   - Use `create_all` for Phase 1 unless migrations are introduced deliberately.

5. Add Pydantic models aligned with existing schemas.
   - Model all nine schema contracts listed above.
   - Preserve strictness where schemas use `additionalProperties: false`.
   - Enforce required fields, enum values, confidence ranges, date-time fields, URI/email validation, and nested objects.
   - Treat these models as type helpers; JSON Schema files remain the validation source of truth for imported files.

6. Add schema registry and file classifier.
   - Load schemas from repository `schemas/`.
   - Map expected filenames to schema files:
     - `company_candidate.json`
     - `contact_candidate.json`
     - `email_draft.json`
     - `fit_evaluation.json`
     - `gate_result.json`
     - `master_cv_profile.json`
     - `policy.json`
     - `send_intent.json`
     - `user_profile.json`
   - Decide and document whether suffixed filenames such as `company_candidate.<id>.json` are accepted in Phase 1. Prefer exact filenames unless the implementation tests the suffix convention explicitly.
   - Unknown JSON files should be recorded as failed imports with a clear `unknown_file_type` validation result.

7. Add JSON validation service.
   - Read each file as UTF-8 JSON.
   - Return structured validation output with status, schema name, error count, field paths, messages, and reason codes.
   - Distinguish:
     - `invalid_json`
     - `unknown_file_type`
     - `schema_validation_failed`
     - `schema_validation_passed`
     - `file_read_failed`

8. Add run output import service.
   - Accept a `run_id` and optional run output path.
   - Resolve default output path as `RUNS_ROOT/<run_id>/output/`.
   - Create or update a `Run` record.
   - Create one `ImportedFile` and one `ValidationResult` per discovered JSON file.
   - Mark the run status as:
     - `imported` if all files validate.
     - `imported_with_errors` if any file fails validation.
     - `import_failed` if the output directory cannot be read or import crashes.
   - Write audit events for import lifecycle and per-file outcomes.
   - Do not normalize valid agent outputs into domain tables.
   - Do not run the deterministic safety gate.

9. Add FastAPI routes.
   - `GET /health` returns service status and `dry_run`.
   - `POST /runs/{run_id}/import` imports `runs/<run_id>/output/`.
   - `GET /runs` lists imported runs.
   - `GET /runs/{run_id}` returns run metadata and imported file summaries.
   - `GET /runs/{run_id}/files` lists imported files.
   - `GET /runs/{run_id}/validation-results` lists validation results.
   - `GET /audit-logs` lists audit events, with optional `run_id` or entity filters if simple to add.

10. Add tests.
    - Use fixture run folders under `backend/tests/fixtures/`.
    - Include at least one valid file for every schema.
    - Include invalid cases for malformed JSON, missing required field, additional property, invalid enum, invalid confidence range, invalid email, invalid URI, and unknown JSON filename.
    - Verify database persistence for `Run`, `ImportedFile`, `ValidationResult`, and `AuditLog`.
    - Verify API responses expose validation errors clearly.
    - Verify `DRY_RUN` defaults to true.
    - Verify no email adapter module, Gmail dependency, or send endpoint exists.

11. Run verification.
    - Run the test suite.
    - Start the FastAPI app locally if useful for manual endpoint checks.
    - Confirm only Phase 1 operational tables are created.

## 6. Test Plan

Unit tests:

- Schema registry loads all nine schema files.
- File classifier maps each expected filename to the correct schema.
- File classifier rejects unknown JSON filenames.
- Validation service accepts valid examples.
- Validation service rejects malformed JSON.
- Validation service rejects missing required properties.
- Validation service rejects additional properties when schemas forbid them.
- Validation service rejects invalid enum values.
- Validation service rejects invalid confidence values outside `0..1`.
- Validation service rejects invalid email and URI formats.

Service tests:

- Importing a valid run creates one `Run`, one `ImportedFile` per JSON file, one passing `ValidationResult` per file, and audit events.
- Importing a mixed valid/invalid run records both successes and failures and sets run status to `imported_with_errors`.
- Importing a missing output directory sets or returns an import failure with a clear error and audit event.
- Re-import behavior is deterministic. The implementation should either update existing records idempotently or create a new import attempt record; choose one behavior and test it.

API tests:

- `GET /health` includes `dry_run: true` by default.
- `POST /runs/{run_id}/import` returns run status and per-file result summary.
- `GET /runs` returns imported run summaries.
- `GET /runs/{run_id}` returns the selected run.
- `GET /runs/{run_id}/files` returns imported file metadata without requiring normalized domain tables.
- `GET /runs/{run_id}/validation-results` returns machine-readable validation errors.
- `GET /audit-logs` returns import audit events.

Boundary tests:

- No endpoint sends email.
- No Gmail package or Gmail adapter is imported.
- No OpenAI package is required.
- No company/contact/send-intent domain tables are created in Phase 1.

## 7. Acceptance Checklist

- [ ] FastAPI app starts.
- [ ] `DRY_RUN` defaults to `true`.
- [ ] All nine JSON schemas are loaded from `schemas/`.
- [ ] Pydantic models are aligned with the current schema contracts.
- [ ] Import service reads `runs/<run_id>/output/`.
- [ ] Valid JSON outputs are accepted and persisted as operational import records.
- [ ] Invalid outputs are rejected with clear machine-readable errors.
- [ ] Runs, imported files, validation results, and audit logs are persisted.
- [ ] API endpoints expose imported runs, imported files, validation results, and audit logs.
- [ ] No normalized domain persistence is implemented.
- [ ] No dedupe logic or send reservations are implemented.
- [ ] No email adapter, Gmail sending, or send endpoint exists.
- [ ] No OpenAI API dependency is added.
- [ ] Tests cover valid and invalid imports.
- [ ] Existing docs and schemas remain unchanged unless a separate task authorizes reconciliation.

## 8. Risks and Mitigations

- Risk: Gate result status names conflict between `docs/SAFETY_GATES.md` and `schemas/gate_result.schema.json`.
  - Mitigation: Phase 1 should validate imported `gate_result.json` against the current schema file without implementing or producing gate results. Record the discrepancy for a later schema/docs reconciliation task.

- Risk: Pydantic models drift from JSON Schema files.
  - Mitigation: Keep JSON Schema validation as the import authority and add tests that compare representative valid and invalid fixtures through both validation paths where practical.

- Risk: Phase 1 accidentally grows into Phase 2 domain persistence.
  - Mitigation: Restrict database models to `Run`, `ImportedFile`, `ValidationResult`, and `AuditLog`. Store raw validated JSON only as imported file data or metadata, not as normalized company/contact/send-intent tables.

- Risk: Importing `send_intent.json` may be mistaken for permission to send.
  - Mitigation: Name API responses and audit actions as validation/import only. Do not add gate execution, reservation, adapter, or send endpoints.

- Risk: Local database setup blocks development.
  - Mitigation: Use a configurable `DATABASE_URL`. Target Postgres for durable development, and allow isolated test overrides.

- Risk: Re-imports create confusing duplicate operational records.
  - Mitigation: Define re-import behavior during implementation. Prefer idempotent updates by `(run_id, relative_path, sha256)` or explicit import-attempt records, then test the chosen behavior.

## 9. Handoff Prompt for the Implementation Agent

You are the Phase 1 implementation agent for this repository.

Read `AGENTS.md`, `README.md`, `docs/ARCHITECTURE.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/AGENT_BOUNDARIES.md`, `docs/SAFETY_GATES.md`, `docs/DATA_MODEL.md`, `docs/CODEX_WORKFLOW.md`, `docs/SEND_INTENT_SPEC.md`, `docs/PHASE_1_TASK_BREAKDOWN.md`, and every file in `schemas/` before editing.

Implement Phase 1 only:

- Add a minimal FastAPI backend skeleton.
- Keep `DRY_RUN=true` as the default.
- Add Pydantic models aligned with the existing schemas.
- Validate imported run output JSON files against the schema files in `schemas/`.
- Add a run output import service for `runs/<run_id>/output/`.
- Persist only `Run`, `ImportedFile`, `ValidationResult`, and `AuditLog`.
- Add API endpoints for inspecting imported runs, imported files, validation results, and audit logs.
- Add tests for valid and invalid imports.

Do not implement Gmail sending, any email adapter, OpenAI API usage, a full frontend, safety gate execution, send reservations, dedupe/domain models, or normalized persistence for companies, contacts, drafts, policies, profiles, send intents, or gate results.

Preserve existing architecture decisions. If you notice contradictions, document them or ask before changing existing docs or schemas. In particular, note that gate result status names currently differ between `docs/SAFETY_GATES.md` and `schemas/gate_result.schema.json`; Phase 1 should validate against the current schema file and not produce gate results.
