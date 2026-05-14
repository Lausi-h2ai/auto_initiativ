# Phase 2 Final Audit

Status: `pass`
Date: 2026-05-14
Scope: `AM-002-002` through `AM-002-007`

## Summary

Phase 2 is ready to close. The repository now has normalized persistence, additive Alembic migrations, deterministic normalization helpers, database-backed dedupe constraints for reservation and contacted outreach state, fake deterministic seed fixtures, and import-to-domain normalization for schema-valid Phase 1 outputs.

The safety boundary remains intact. I found no gate execution service, no send endpoint, no email adapter, no Gmail integration, and no OpenAI API dependency.

## Evidence

- Migration strategy and Alembic workflow are documented in `adr/0001-alembic-migrations.md`.
- Operational Phase 1 tables remain intact: `runs`, `imported_files`, `validation_results`, and `audit_logs`.
- Phase 2 domain tables exist for snapshots, companies, contacts, fit evaluations, email drafts, send intents, imported gate results, send reservations, and outreach records.
- Dedupe is enforced in database constraints on `send_reservations` and `outreach_records`, not by prompts.
- Recipient email, company domain, company name, and company policy key normalization are deterministic and covered by tests.
- Seed fixtures use fake local data and do not create gate results, reservations, outreach records, adapters, or send paths.
- Import normalization only runs after all expected imported files pass schema validation.
- Imported gate results are stored as data only. No Phase 2 code computes or approves gate results.

## Verification

Command:

```powershell
uv run --python 3.12 --extra test pytest -q --basetemp=.tmp\pytest-phase2-audit
```

Result:

```text
79 passed, 1 skipped in 9.38s
```

The skipped test is the optional Postgres partial-index integration test, which only runs when `POSTGRES_TEST_DATABASE_URL` is configured. SQLite-backed migration, normalization, dedupe, seed fixture, import, API, schema, and boundary tests all passed.

## Acceptance Result

| Check | Result | Notes |
| --- | --- | --- |
| Normalized persistence complete | Pass | Domain tables and import links are present. |
| Dedupe constraints complete | Pass | Reservation and contacted outreach uniqueness are enforced by partial unique indexes. |
| Seed fixtures complete | Pass | Fake deterministic fixture graph persists through domain models. |
| Import-to-domain normalization complete | Pass | Valid outputs normalize; invalid outputs do not create domain rows. |
| No gate execution | Pass | Gate results are imported data only. |
| No email adapter or Gmail sending | Pass | Boundary tests and source inspection confirm absence. |
| No OpenAI API dependency | Pass | `pyproject.toml` has no OpenAI dependency; boundary tests assert this. |
| Existing tests pass | Pass | Full suite passed on 2026-05-14. |

## Remaining Risks Before Phase 3

1. Phase 3 must implement the deterministic `evaluate_only` gate without creating reservations or adapter paths.
2. Gate tests should define a full reason-code matrix before any future `reserve_for_send` work.
3. Postgres partial unique constraints should be run in CI or a configured local Postgres environment before relying on production-like behavior.
4. `RunImportService` and `DomainNormalizationService` are now central integration points. They are acceptable for Phase 2, but Phase 3 should keep gate logic separate instead of expanding import normalization into a policy engine.
5. The gate-status schema/docs reconciliation dependency is already closed by `AM-003-001`; Phase 3 can proceed with `AM-003-002`.

## Decision

Phase 2 is complete and ready for Phase 3 deterministic gate implementation.

Recommended next tick: `AM-003-002: Implement Evaluate-Only Gate`.
