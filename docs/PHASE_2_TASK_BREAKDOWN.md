# Phase 2 Task Breakdown

## 1. Phase 2 Objective

Phase 2 makes Postgres-oriented normalized persistence the source of truth for outreach state while preserving the Phase 1 import boundary.

The goal is to add durable domain entities, deterministic normalization fields, and database-enforced dedupe constraints for companies, contacts, snapshots, drafts, send intents, and future-compatible reservation records. Phase 2 must not execute the safety gate and must not add any email sending path.

## 2. Current Phase 1 Baseline

Phase 1 is complete and audited as ready for Phase 2.

Current implemented backend state:

- FastAPI backend skeleton under `backend/app/`.
- `DRY_RUN=true` default.
- JSON Schema registry and validation for expected agent output files in `schemas/`.
- Import service for `runs/<run_id>/output/`.
- Operational persistence only:
  - `runs`
  - `imported_files`
  - `validation_results`
  - `audit_logs`
- API inspection endpoints for runs, imported files, validation results, and audit logs.
- Tests covering valid imports, invalid JSON, schema failures, missing files, unsupported run types, audit logging, dry-run default, and no Gmail/OpenAI/email adapter boundary.

Current deliberate gaps:

- No normalized company/contact/profile/policy/draft/send-intent domain tables.
- No dedupe constraints.
- No send reservations.
- No safety gate execution.
- No email adapter or sending code.
- No OpenAI API dependency.
- Default local database remains SQLite for developer convenience, while Phase 2 target persistence is Postgres.

## 3. Explicit In-Scope Items

Phase 2 implementation work should cover:

- Normalized source-of-truth database models for:
  - immutable user profile snapshots
  - immutable master CV profile snapshots
  - immutable policy snapshots
  - companies
  - contacts
  - fit evaluations
  - email drafts
  - send intents
  - future-compatible gate result records as persisted data only
  - future-compatible send reservations for dedupe/reservation constraints only
  - normalized audit links needed for traceability
- Postgres-oriented persistence and migrations.
- A migration strategy decision before model implementation.
- Deterministic normalized fields for:
  - recipient emails
  - company domains
  - company policy keys
- Database-level dedupe constraints for duplicate recipients, duplicate companies, and active reservations.
- Fake, safe seed fixtures for local development and tests.
- Import-to-domain normalization for schema-valid Phase 1 imported outputs, if selected for Phase 2 after the core models and constraints are in place.
- Tests proving duplicate recipient and duplicate company constraints are enforced by the database.
- Tests preserving Phase 1 import behavior.

## 4. Explicit Out-of-Scope Items

Phase 2 must not include:

- Gmail sending.
- Gmail API calls.
- OpenAI API usage or dependency additions.
- Frontend or dashboard implementation.
- Phase 3 safety gate execution.
- Real email adapters.
- Fake email adapters.
- Autonomous sending.
- Any send endpoint or adapter handoff.
- Treating a `send_intent` as approved, safe, or sendable.
- Reconciliation of gate status schema/docs except as a recorded Phase 3 dependency.
- Production-like destructive database mutations outside application logic.

## 5. Proposed File Structure

Recommended implementation files for later Phase 2 ticks:

```text
backend/app/db/models.py
backend/app/db/domain_models.py              # optional split if models.py becomes too large
backend/app/db/normalization.py              # deterministic email/domain/company key helpers
backend/app/db/session.py                    # Postgres-compatible engine/session updates if needed
backend/app/imports/domain_normalizer.py     # optional import-to-domain mapping service
backend/app/seed/fixtures.py                 # safe local seed data, if a seed module is chosen
backend/tests/test_domain_models.py
backend/tests/test_dedupe_constraints.py
backend/tests/test_normalization.py
backend/tests/test_import_domain_normalization.py
backend/tests/fixtures/domain_seed/
adr/ADR-0001-migration-strategy.md           # exact number/name chosen by implementer
alembic.ini                                  # if Alembic is adopted
backend/migrations/                          # if Alembic is adopted
```

Keep existing Phase 1 files intact unless a Phase 2 task explicitly changes them. In particular, keep `runs`, `imported_files`, `validation_results`, and `audit_logs` as auditable operational import records.

## 6. Data Model Tasks In Recommended Order

1. Confirm ORM and migration baseline.
   - Continue with SQLModel unless the migration ADR chooses plain SQLAlchemy.
   - Decide how Postgres tests will run locally and in CI-like local execution.

2. Decide contacted-state dedupe ownership before writing models or migrations.
   - Choose the database object that represents "previously contacted recipient" and "previously contacted company" state under policy.
   - Explicitly decide whether contacted uniqueness lives in dedicated outreach/contact history tables, send reservations, sent message records, status-backed indexes on send intents, or a combination of these.
   - Document which table owns recipient-level uniqueness by normalized recipient email and which table owns company-level uniqueness by company policy key.
   - Document how active reservation uniqueness differs from completed-contact uniqueness, including which statuses participate in each partial unique index.
   - Do not rely on candidate company/contact rows to enforce "previously contacted" rules, because imported research candidates must not prematurely block later review or outreach planning.
   - Complete this decision before authoring migrations for companies, contacts, send intents, reservations, sent messages, or contacted-history records.

3. Add immutable snapshot tables.
   - `user_profile_snapshots`
   - `master_cv_profile_snapshots`
   - `policy_snapshots`
   - Store source schema version, external snapshot ID from JSON, raw validated JSON, content hash, imported file link, created/imported timestamps, and immutable status metadata.
   - Do not update snapshot content in place. New imported versions create new rows.

4. Add company table.
   - Store external `company_id`, display name, raw domain, normalized domain, normalized company name, policy company key, source refs, confidence, review flags, raw validated JSON, and import provenance.
   - Make normalized fields first-class columns, not only computed in service code.

5. Add contact table.
   - Store external `contact_id`, company FK, name, role title, raw email, normalized recipient email, email source, profile URL, source refs, confidence, review flags, and raw validated JSON.
   - Preserve contact email provenance and review/block metadata for Phase 3.

6. Add fit evaluation table.
   - Store external `evaluation_id`, company FK, profile snapshot FK where resolvable, policy snapshot FK where resolvable, fit score, decision, reasons/risks JSON, source refs, confidence, review flags, and raw validated JSON.
   - This remains data storage only; it does not decide whether outreach is allowed.

7. Add email draft table.
   - Store external `draft_id`, company FK, contact FK, subject, body text/html, tone, claim refs, source refs, attachments JSON, confidence, review flags, and raw validated JSON.
   - Do not validate claim legitimacy beyond referential storage in Phase 2 unless it is part of deterministic import normalization.

8. Add send intent table.
   - Store external `intent_id`, run ID, company FK, contact FK, draft FK, recipient raw email, normalized recipient email, subject/body, attachment refs, source refs, claim refs, policy snapshot FK, user profile snapshot FK, master CV snapshot FK, confidence, review flags, created_by, raw validated JSON, and status such as `imported` or `needs_gate_evaluation`.
   - Do not run the gate. Do not reserve. Do not send.

9. Add future-compatible gate result table as persisted records only.
   - This table may store imported `gate_result.json` for auditability, but Phase 2 must not compute gate results.
   - Record the known schema/docs mismatch as a Phase 3 blocker before executable gate work. Resolved in `AM-003-001`.

10. Add send reservation table for constraints only.
   - Model reservation identity, send intent FK, normalized recipient email, company FK, company policy key, policy snapshot FK, status, created_at, and released/expired timestamps if needed.
   - Phase 2 may insert test records directly to prove constraints, but application behavior must not create real reservations.

11. Add normalized audit links.
   - Preserve existing `audit_logs`.
   - Add nullable links or structured metadata from domain rows back to `Run`, `ImportedFile`, and validation result IDs where useful.
   - Keep audit append-only.

## 7. Migration Strategy Task

Create a dedicated migration strategy tick before adding tables.

Recommended decision:

- Adopt Alembic now for Phase 2 because Postgres-specific constraints, partial unique indexes, JSON columns, and future transactional reservation behavior need explicit migration history.

The migration strategy tick should decide and document:

- Whether to keep SQLModel with Alembic autogenerate or switch to SQLAlchemy declarative models.
- How migrations are generated, reviewed, and applied locally.
- How SQLite remains supported, if at all, for fast tests.
- Which tests require Postgres because partial indexes and concurrency-sensitive constraints are not portable.
- How to avoid destructive migrations while Phase 1 operational tables already exist.

Acceptance for the migration strategy tick:

- ADR exists if Alembic or a new workflow is adopted.
- Empty initial migration or baseline migration strategy is clear.
- Existing Phase 1 tests still pass.
- No production-like destructive migration is introduced.

## 8. Dedupe And Normalization Rules

Normalization must be deterministic, covered by tests, and applied before persistence.

Recipient email:

- Trim surrounding whitespace.
- Lowercase the full address.
- Reject invalid email syntax at schema/import boundary; do not guess corrections.
- Store both raw and normalized values.
- Do not provider-normalize aliases such as Gmail dots or plus tags in Phase 2 unless a later ADR explicitly adopts that behavior.

Company domain:

- Trim whitespace.
- Lowercase.
- Parse host from URL-like inputs when present.
- Strip scheme, path, query, fragment, port, trailing dot, and leading `www.`.
- Normalize IDN domains using IDNA/punycode.
- Store both raw and normalized values.
- If domain is absent or invalid, mark the record as needing review rather than inventing a domain.

Company policy key:

- Prefer `domain:<normalized_domain>` when a normalized domain exists.
- Otherwise use `name:<casefolded-normalized-company-name>`.
- Trim and collapse internal whitespace for name keys.
- Store the chosen key and key kind.
- Do not merge companies by fuzzy name matching in Phase 2.

Database constraints:

- Unique external IDs where stable within their entity type, such as `company_id`, `contact_id`, `draft_id`, `intent_id`, and snapshot IDs.
- Unique normalized recipient email for contacted recipients when policy forbids repeat contact. If policy windows are implemented later, model this as prior outreach/reservation state, not prompt logic.
- Unique normalized company policy key for contacted companies when policy forbids repeat company outreach.
- Unique active reservation per normalized recipient email.
- Unique active reservation per company policy key when company-level dedupe applies.
- Use Postgres partial unique indexes for active reservations, for example uniqueness only where `status` is in active states such as `active` or `reserved`.

Phase 2 should distinguish persisted candidates from completed outreach state. If a company/contact is merely imported as a candidate, unique source IDs and normalized lookup indexes are enough. The stricter "previously contacted" constraints should be represented on future outreach/reservation/contacted records so research candidates do not block each other prematurely.

## 9. Import-To-Domain Normalization Plan

Import-to-domain normalization is in scope only after core tables, migrations, normalization helpers, and constraints exist.

Recommended plan:

1. Keep Phase 1 raw import records as the audit source.
2. Normalize only schema-valid files.
3. Map imported files in dependency order:
   - `user_profile.json` -> `user_profile_snapshots`
   - `master_cv_profile.json` -> `master_cv_profile_snapshots`
   - `policy.json` -> `policy_snapshots`
   - `company_candidate.json` -> `companies`
   - `contact_candidate.json` -> `contacts`
   - `fit_evaluation.json` -> `fit_evaluations`
   - `email_draft.json` -> `email_drafts`
   - `send_intent.json` -> `send_intents`
   - `gate_result.json` -> imported gate result record only, with no execution
4. Store unresolved references explicitly with a `needs_review` or `unresolved_reference` status rather than inventing records.
5. Link each domain row to its run ID and imported file ID.
6. Keep import idempotent by external ID plus content hash or replacement version policy.
7. Write audit events for domain normalization success/failure.

Open implementation choice:

- Either normalize during `RunImportService.import_run()` after schema validation succeeds, or add a separate `DomainNormalizationService` invoked after import. Prefer a separate service to keep Phase 1 validation behavior readable and testable.

## 10. Test Plan

Migration and persistence:

- Existing Phase 1 tests still pass.
- Migration applies to an empty Postgres database.
- Migration applies without dropping Phase 1 operational tables.
- ORM metadata and migration schema stay aligned.

Normalization:

- Email normalization trims and lowercases.
- Email normalization rejects invalid values through existing schema/import validation.
- Domain normalization handles scheme, path, port, trailing dot, `www.`, uppercase, and IDN.
- Company policy key prefers normalized domain over normalized name.
- Name fallback trims, casefolds, and collapses whitespace.

Dedupe constraints:

- Duplicate active recipient reservation fails for the same normalized email.
- Duplicate active company reservation fails for the same company policy key.
- Released/cancelled/expired reservations do not block new active reservations if that status model is adopted.
- Duplicate contacted recipient fails when repeat contact is forbidden.
- Duplicate contacted company fails when company repeat outreach is forbidden.
- Duplicate raw emails with different case/spacing fail because normalized email matches.
- Duplicate raw domains with different URL forms fail because normalized domain/key matches.

Import-to-domain normalization:

- Schema-valid company/contact/draft/send-intent files create normalized domain rows.
- Schema-invalid files create no domain rows.
- Missing referenced company/contact/draft/snapshot marks normalization as failed or needs review with machine-readable reason codes.
- Raw `ImportedFile` and `ValidationResult` rows remain inspectable.
- Re-import behavior remains deterministic and does not silently erase prior audit history.

Boundaries:

- No OpenAI dependency is declared.
- No Gmail dependency is declared.
- No email adapter module or configuration exists.
- No send endpoint exists.
- Phase 2 send intent import does not run gate execution.
- Phase 2 reservation model tests do not create adapter handoff behavior.

## 11. Acceptance Checklist

- [ ] Migration strategy is decided and documented.
- [ ] Postgres-oriented migrations exist for Phase 2 tables.
- [ ] Phase 1 operational tables remain intact.
- [ ] Immutable profile, master CV, and policy snapshot tables exist.
- [ ] Company and contact tables store raw and normalized dedupe fields.
- [ ] Draft, fit evaluation, and send intent tables store source refs, confidence, review flags, raw JSON, and provenance links.
- [ ] Future-compatible gate result records are persisted only as data; no gate is executed.
- [ ] Send reservation table has database constraints for active recipient/company uniqueness.
- [ ] Recipient email, company domain, and company policy key normalization are deterministic and tested.
- [ ] Database constraints, not prompts, enforce dedupe.
- [x] Seed fixtures are fake, safe, and deterministic.
- [x] Import-to-domain normalization handles only schema-valid outputs.
- [ ] Duplicate recipient and duplicate company tests fail at the database boundary.
- [x] Existing import tests still pass.
- [x] Boundary tests still prove no Gmail, no OpenAI API dependency, no adapter, and no sending path.

## 12. Risks And Mitigations

Risk: SQLite tests can give false confidence for Postgres partial indexes and JSON behavior.

Mitigation: Keep fast SQLite-compatible tests where useful, but require Postgres-backed tests for migration and dedupe constraints.

Risk: Import normalization could blur the Phase 1 audit boundary.

Mitigation: Preserve `ImportedFile` and `ValidationResult` as raw operational records. Domain rows must link back to imported files and never replace raw import evidence.

Risk: Candidate dedupe could incorrectly block research of the same company before outreach happens.

Mitigation: Separate candidate uniqueness from contacted/reservation uniqueness. Enforce "previously contacted" on outreach state, not on every candidate row.

Risk: Gate result status mismatch could leak into Phase 2 tables. Resolved in `AM-003-001`.

Mitigation: Store imported gate results only as raw/future-compatible records. Do not build executable gate behavior until Phase 3 contracts are reconciled.

Risk: Normalization choices could be too clever and merge unrelated companies.

Mitigation: Avoid fuzzy matching in Phase 2. Use deterministic domain-first keys and conservative name fallback.

Risk: Send reservations could imply sending is available.

Mitigation: Implement reservation tables and constraints only. No public API, gate mode, adapter, or sending flow should create or consume reservations in Phase 2.

## 13. Recommended Role/Tick Split For Phase 2 Implementation

1. `AM-002-002` Migration Strategy
   - Roles: `RESEARCHER`, `IMPLEMENTER`, `REVIEWER`
   - Output: ADR and minimal migration setup decision.

2. `AM-002-003A` Snapshot And Core Domain Models
   - Roles: `IMPLEMENTER`, `TESTER`, `REVIEWER`
   - Output: snapshot, company, contact, evaluation, draft, and send intent tables without reservation behavior.

3. `AM-002-003B` Future-Compatible Reservation And Gate Result Records
   - Roles: `IMPLEMENTER`, `TESTER`, `REVIEWER`
   - Output: persisted data models and constraints only; no gate execution.

4. `AM-002-004` Normalization And Dedupe Constraints
   - Roles: `IMPLEMENTER`, `TESTER`, `REVIEWER`
   - Output: normalization helpers, DB constraints, and duplicate recipient/company tests.

5. `AM-002-005` Seed Fixtures
   - Roles: `IMPLEMENTER`, `TESTER`
   - Output: fake local seed fixtures and deterministic fixture tests.

6. `AM-002-006` Import-To-Domain Normalization
   - Roles: `IMPLEMENTER`, `TESTER`, `REVIEWER`
   - Output: schema-valid import mapping into domain tables with audit links.

7. Phase 2 Audit
   - Roles: `AUDITOR`
   - Output: Phase 2 audit report confirming readiness for Phase 3 and listing gate-status reconciliation as the first Phase 3 dependency.

## 14. Handoff Prompt For The Phase 2 Implementation Agent

```text
You are the IMPLEMENTER for the next Phase 2 implementation tick.

Read:
- CHARTER.md
- AGENTS.md
- BACKLOG.md
- BUGS.md
- docs/AUTOMODE.md
- roles/IMPLEMENTER.md
- docs/PHASE_2_TASK_BREAKDOWN.md
- docs/IMPLEMENTATION_PLAN.md
- docs/ARCHITECTURE.md
- docs/DATA_MODEL.md
- docs/SAFETY_GATES.md
- docs/SEND_INTENT_SPEC.md
- docs/CODEX_WORKFLOW.md
- schemas/
- backend/app/db/models.py
- backend/app/imports/import_service.py
- backend/tests/

Goal:
Implement only the assigned Phase 2 tick from docs/PHASE_2_TASK_BREAKDOWN.md. Keep the work bounded to normalized persistence, migrations, deterministic normalization, database constraints, fixtures, or import-to-domain normalization as assigned.

Non-negotiable boundaries:
- Do not send email.
- Do not call Gmail.
- Do not add Gmail, SMTP, OpenAI, or email adapter dependencies.
- Do not implement Phase 3 safety gate execution.
- Do not add real or fake email adapters.
- Do not create autonomous sending.
- Do not decide that any send intent is safe, approved, or sendable.

Before editing:
- Inspect the current repository.
- Validate assumptions against docs and schemas.
- Confirm the allowed file scope for the specific tick.

Expected verification:
- Run relevant backend tests.
- Include Postgres-backed tests when the tick touches migrations, partial indexes, or dedupe constraints.
- Confirm existing Phase 1 import behavior and boundary tests still pass.

Final response:
- List changed files.
- List tests run and results.
- State assumptions and remaining risks.
```
