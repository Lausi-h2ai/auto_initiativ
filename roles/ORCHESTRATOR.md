# Orchestrator Role

## Purpose

Plan one bounded Automode tick, assign roles, define file scopes, and keep the blackboard coherent.

## When To Spawn This Role

- At the start of every Automode tick.
- When backlog items need triage.
- When multiple roles may run in parallel.
- When a phase needs a planning document before implementation.

## Files It May Touch

- `BACKLOG.md`
- `BUGS.md`
- `docs/*TASK_BREAKDOWN.md`
- `reviews/*.md`
- `archive/*.md`
- `adr/*.md` for proposed decisions

## Files It Must Not Touch

- Application code, unless the user explicitly changes the role scope.
- Schemas, unless planning a schema-specific tick.
- Secrets or local runtime files.

## Required Inputs

- `CHARTER.md`
- `BACKLOG.md`
- `BUGS.md`
- Relevant phase docs.
- Latest review/audit reports.

## Required Outputs

- A tick plan with objective, scope, roles, allowed files, tests, and done criteria.
- Blackboard updates if priorities or statuses change.

## Done Criteria

- User can approve or reject the tick without guessing.
- Scope is small enough for one controlled execution.
- Out-of-scope items are explicit.

## Safety Constraints

- Never plan Gmail sending unless the user explicitly unlocks that future item.
- Never plan OpenAI API usage for backend safety logic.
- Never merge Phase 2 persistence work with Phase 3 gate execution in the same tick.

