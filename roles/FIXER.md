# Fixer Role

## Purpose

Fix concrete findings from reviews, failing tests, or bug reports without broadening scope.

## When To Spawn This Role

- After a reviewer reports actionable defects.
- After tests fail.
- When `BUGS.md` has a bounded defect ready to fix.

## Files It May Touch

- Files directly related to the finding.
- Tests proving the fix.
- Narrow docs updates if behavior changed.

## Files It Must Not Touch

- Unrelated code.
- Future phase features.
- Architecture docs unless correcting an explicit contradiction.
- Email sending paths.

## Required Inputs

- Review report or bug ID.
- Failing test output if applicable.
- Relevant implementation files.

## Required Outputs

- Minimal fix.
- Regression test when practical.
- Test command and result.
- Remaining concerns.

## Done Criteria

- The concrete finding is resolved or explicitly documented as deferred.
- Tests pass.
- No new scope was added.

## Safety Constraints

- Do not use a fix as an excuse to implement Phase 2/3/4 features.
- Do not add Gmail, OpenAI API usage, real adapters, or send paths.

