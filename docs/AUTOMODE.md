# Automode Operating Guide

Automode is the repository operating system for Phase 2 and later. It uses markdown files, role prompts, bounded ticks, review reports, and git as the log.

## Charter

`CHARTER.md` is the top-level operating manual. Every role must read it before a tick. If a task conflicts with the charter, the charter wins unless the user explicitly updates it.

## Roles

Roles live in `roles/`.

Use roles to keep work bounded:

- `ORCHESTRATOR`: plan ticks and split work.
- `IMPLEMENTER`: make scoped code/docs changes.
- `REVIEWER`: review against architecture, safety, and scope.
- `TESTER`: strengthen tests and verify behavior.
- `FIXER`: address concrete findings and failing tests.
- `AUDITOR`: decide whether a phase/tick is complete.
- `RESEARCHER`: gather facts and write decision memos.

Roles are not permanent people. Spawn only the role needed for the tick.

## Blackboard

The blackboard is the shared project state in markdown:

- `CHARTER.md`: operating contract.
- `BACKLOG.md`: phase work and next recommended tick.
- `BUGS.md`: known defects.
- `reviews/`: tick reviews and audits.
- `archive/`: completed tick summaries.
- `adr/`: architecture decisions.

State belongs on the blackboard, not in a chat thread.

## Tick

A tick is a bounded work interval with:

- One clear objective.
- One approved scope.
- Assigned roles.
- Explicit files allowed to change.
- Tests or review criteria.
- A final artifact.

Suggested tick size for this project: one small planning or implementation unit, usually 30-120 minutes of agent work.

## Log

Each tick must leave a log artifact:

- A review report in `reviews/`.
- A completion summary in `archive/`.
- An ADR in `adr/` when architecture decisions change.
- A git commit when the user asks for one.

If a tick produces no committable result, log that honestly and create a follow-up bug or backlog item.

## Standard Tick Loop

1. Orchestrator reads `CHARTER.md`, `BACKLOG.md`, `BUGS.md`, and relevant docs.
2. Orchestrator proposes one bounded tick plan.
3. User approves, edits, or rejects the plan.
4. User/Orchestrator spawns the needed role agents.
5. Roles execute in bounded file scopes.
6. Tester runs relevant tests.
7. Reviewer checks result against charter, architecture, and scope.
8. Fixer handles concrete findings if needed.
9. Auditor or Orchestrator writes tick summary.
10. Blackboard is updated: close done items, add bugs/findings, archive completed tick.
11. User decides whether to commit.

## Starting One Codex Run

Use this pattern:

```text
You are the <ROLE> for tick <ID>.

Read:
- CHARTER.md
- BACKLOG.md
- BUGS.md
- role file in roles/
- relevant docs and code listed in the tick

Goal:
<one bounded objective>

Scope:
<files/directories allowed>

Do not:
<out-of-scope constraints>

Done when:
<objective, tests, report, or artifact>
```

## Reviewing A Tick

A review should answer:

- Did the tick stay in scope?
- Did it preserve "Agents produce files. Programs make decisions"?
- Did it add Gmail, OpenAI API usage, real sending, or Phase creep?
- Did tests pass?
- Are database constraints and migrations safe?
- Are audit logs preserved?
- Are docs/schemas/code consistent?
- What must be fixed before the next tick?

Write review reports to `reviews/`.

## What Counts As Done

A tick is done when:

- The requested artifact exists.
- Tests or review checks passed.
- No out-of-scope features were added.
- The blackboard reflects the new state.
- The final answer lists changed files, tests run, assumptions, and remaining risks.

## What Must Never Be Delegated

Do not delegate:

- Authorization to send real email.
- Gmail credential handling.
- Decisions to bypass the safety gate.
- Approval of unsupported user career facts.
- Fundamental architecture pivots without user checkpoint.
- Secrets management.
- Production database mutation outside application logic.
- Unlocking locked future backlog items.

Agents may propose these decisions, but the user must approve them and deterministic program logic must enforce them.

## Archiving Completed Ticks

When a tick is complete:

1. Create `archive/tick-<id>.md`.
2. Include objective, roles used, files changed, tests run, result, follow-ups, and commit hash if committed.
3. Mark backlog item as `done` or update with remaining work.
4. Move new defects to `BUGS.md`.
5. Keep review reports in `reviews/`.

