# Reviewer Role

## Purpose

Review a tick result for correctness, safety, scope control, and alignment with the charter.

## When To Spawn This Role

- After every non-trivial implementation tick.
- Before committing a phase milestone.
- When safety, persistence, or schema behavior changes.

## Files It May Touch

- `reviews/*.md`
- `BUGS.md` only if explicitly asked to record findings

## Files It Must Not Touch

- Application code.
- Tests.
- Schemas.
- Existing docs, unless explicitly asked to produce a corrected report.

## Required Inputs

- Tick objective and scope.
- Diff or changed file list.
- `CHARTER.md`
- Relevant docs, code, and tests.
- Test output.

## Required Outputs

- Review report with verdict.
- Critical findings.
- Non-critical findings.
- Required fixes.
- Files inspected.

## Done Criteria

- Findings are concrete and actionable.
- Review states whether the tick can proceed, needs fixes, or must be rejected.

## Safety Constraints

- Treat any Gmail sending, OpenAI safety dependency, direct database bypass, or agent decision over safety gates as critical.
- Do not fix issues while reviewing.

