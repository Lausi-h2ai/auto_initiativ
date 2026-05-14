# Tick 002 Orchestrator Plan

## Tick Objective

Execute Automode Tick 002 as a bounded Phase 2 planning tick for `AM-002-001`.

The tick must produce a concrete Phase 2 implementation plan for normalized database models, migrations, and deterministic dedupe constraints. It must not implement Phase 2 code.

The planning output must preserve the repository boundary: agents produce files, while backend programs own database state, dedupe rules, policy enforcement, safety gates, audit logs, and all irreversible decisions.

## In Scope

- Plan the Phase 2 persistence work described in `docs/IMPLEMENTATION_PLAN.md`.
- Identify the exact Phase 2 entities to model from `docs/DATA_MODEL.md`:
  - immutable profile snapshots
  - immutable master CV profile snapshots
  - immutable policy snapshots
  - companies
  - contacts
  - fit evaluations
  - email drafts
  - send intents
  - gate result records as future-compatible persisted records only
  - send reservations as future-compatible dedupe/reservation records only
  - audit logs and links needed for traceability
- Define deterministic normalization and dedupe requirements for recipient email, company domain, company policy key, and active reservations.
- Define the migration strategy decision that must be made before implementation.
- Define the test plan for duplicate recipient and duplicate company constraints.
- Separate Phase 2 persistence and dedupe from Phase 3 safety gate execution.
- Carry forward Phase 1 audit risks, especially Postgres migration work and the gate status mismatch that must be resolved before Phase 3.
- Keep the output suitable for follow-on implementation ticks.

## Out Of Scope

- Application code changes.
- Dependency changes.
- Database migrations or model implementation.
- Schema edits.
- Backend API changes.
- Seed fixture implementation.
- Dashboard work.
- Codex run orchestration implementation.
- Safety gate execution.
- Phase 3 gate status reconciliation implementation.
- Email adapter work.
- Gmail calls or Gmail sending.
- OpenAI API usage or dependency addition.
- Any production or local database mutation outside existing application behavior.
- Any irreversible action.

## Role Sequence

1. `ORCHESTRATOR`
   - Read the required operating, phase, data model, safety, send intent, backlog, bug, and audit documents.
   - Create this tick plan.
   - Define role ownership, file scopes, artifacts, done criteria, and stop condition.

2. `IMPLEMENTER`
   - Produce the Phase 2 planning artifact only.
   - Recommended target: `docs/PHASE_2_TASK_BREAKDOWN.md`.
   - The artifact should be concrete enough to guide later implementation ticks, including entities, constraints, migration choices to decide, and tests.
   - No code, dependency, schema, or database changes.

3. `TESTER`
   - Review the planning artifact for testability.
   - Confirm it lists focused tests for duplicate recipient email, duplicate company domain/key, active send reservation uniqueness, normalization behavior, and preservation of Phase 1 import behavior.
   - Do not write or run application tests unless the implemented artifact unexpectedly touches code. This tick should require documentation review only.

4. `REVIEWER`
   - Review the planning artifact against `CHARTER.md`, `AGENTS.md`, `docs/IMPLEMENTATION_PLAN.md`, `docs/DATA_MODEL.md`, `docs/SAFETY_GATES.md`, and `docs/SEND_INTENT_SPEC.md`.
   - Verify it does not merge Phase 2 persistence with Phase 3 gate execution.
   - Verify no Gmail, OpenAI API, email adapter, or sending behavior is introduced.
   - Write findings to a review artifact if needed.

5. `FIXER`
   - Address only concrete reviewer or tester findings in the planning artifact.
   - Do not broaden scope.
   - Do not implement code.

6. `AUDITOR`
   - Decide whether Tick 002 is complete.
   - Confirm all changed files are allowed.
   - Confirm the tick stopped at Phase 2 planning.
   - Confirm follow-on implementation remains separate.

## Allowed File Changes Per Role

`ORCHESTRATOR`:

- `reviews/tick-002-orchestrator-plan.md`

`IMPLEMENTER`:

- `docs/PHASE_2_TASK_BREAKDOWN.md`
- Optional, only if a planning decision needs a formal proposal: `adr/*.md`

`TESTER`:

- Optional review note only: `reviews/tick-002-tester-review.md`

`REVIEWER`:

- Optional review note only: `reviews/tick-002-reviewer-report.md`

`FIXER`:

- `docs/PHASE_2_TASK_BREAKDOWN.md`
- Any optional Tick 002 ADR created by the implementer, if the finding is about that ADR

`AUDITOR`:

- `reviews/tick-002-audit.md`
- Optional completion archive if explicitly chosen by the running tick owner: `archive/tick-002.md`

For this orchestrator run specifically, worker ownership is restricted to `reviews/tick-002-orchestrator-plan.md`. No other file may be modified by this role.

## Required Artifacts

- Required from this Orchestrator role:
  - `reviews/tick-002-orchestrator-plan.md`

- Required from the full Tick 002 execution:
  - `docs/PHASE_2_TASK_BREAKDOWN.md`

- Optional if needed:
  - `adr/*.md` for a migration strategy proposal or decision.
  - `reviews/tick-002-tester-review.md`
  - `reviews/tick-002-reviewer-report.md`
  - `reviews/tick-002-audit.md`
  - `archive/tick-002.md`

## Done Criteria

This Orchestrator role is done when:

- `reviews/tick-002-orchestrator-plan.md` exists.
- The plan identifies the tick objective, scope, role sequence, file ownership, required artifacts, safety constraints, done criteria, and stop condition.
- The plan explicitly limits this role to the single requested file.

Full Tick 002 is done when:

- A concrete Phase 2 planning artifact exists.
- The plan identifies exact Phase 2 entities and relationships.
- The plan defines migration approach options or a required ADR decision.
- The plan defines database-level dedupe constraints and normalization rules.
- The plan lists tests for duplicate recipients, duplicate companies, active reservations, normalization, and unchanged Phase 1 import behavior.
- The plan separates Phase 2 persistence/dedupe from Phase 3 safety gate execution.
- The plan keeps Gmail sending, OpenAI API usage, adapter work, and gate execution out of scope.
- Any reviewer/tester findings are either fixed or recorded as follow-up risks.
- The auditor confirms the tick stopped after planning.

## Safety Constraints

- Codex agents must never send email.
- Codex agents must never call Gmail.
- Do not add an email adapter or any sending path.
- Do not add an OpenAI API dependency.
- Do not run or implement safety gate execution.
- Do not create send reservations through application behavior in this tick.
- Do not claim a send intent is safe or approved.
- Do not bypass backend validation.
- Do not mutate production-like database state.
- Do not invent user career facts.
- Preserve immutable snapshot concepts for profile, master CV profile, and policy records.
- Preserve source references, confidence values, review flags, and provenance requirements for any future agent output consumed by code.
- Keep dedupe enforcement as a database responsibility, not a prompt responsibility.
- Treat `sent` and `send_failed` as future adapter/send-result statuses, not Phase 2 gate statuses.

## Stop Condition

Stop after Tick 002 planning artifacts are produced, reviewed, fixed if necessary, and audited.

Do not continue into Phase 2 implementation. Do not start `AM-002-002`, `AM-002-003`, or any later backlog item unless the user explicitly starts a new tick.
