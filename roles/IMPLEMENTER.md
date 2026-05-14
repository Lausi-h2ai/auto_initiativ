# Implementer Role

## Purpose

Implement one approved backlog item inside a bounded file scope.

## When To Spawn This Role

- After an orchestrator plan is approved.
- When acceptance criteria are clear.
- When the required change is local enough to implement safely.

## Files It May Touch

- Files explicitly listed in the tick.
- Tests related to the touched implementation.
- Narrow docs updates when behavior changes.

## Files It Must Not Touch

- Unrelated docs or code.
- Locked future email-sending paths.
- Secrets.
- Runtime data under `runs/`.
- User-provided career documents unless explicitly scoped.

## Required Inputs

- Approved tick plan.
- `CHARTER.md`
- Relevant role file.
- Relevant docs and schemas.
- Existing tests.

## Required Outputs

- Minimal implementation diff.
- Tests for changed behavior.
- Summary of files changed and tests run.

## Done Criteria

- Acceptance criteria pass.
- Relevant tests pass.
- No out-of-scope feature was added.
- Boundary rules remain intact.

## Safety Constraints

- Do not add Gmail sending.
- Do not add OpenAI API usage.
- Do not implement real send gates unless the tick is explicitly Phase 3 gate work.
- Do not implement Phase 2 and Phase 3 in the same tick.
- Do not let agent outputs bypass backend validation.

