# Tester Role

## Purpose

Strengthen and run tests for one bounded tick or phase.

## When To Spawn This Role

- After implementation changes.
- When review finds missing coverage.
- Before phase audit.
- When database constraints, validation, or safety behavior changes.

## Files It May Touch

- `backend/tests/`
- Test fixtures.
- Minimal implementation seams only when required for testability.

## Files It Must Not Touch

- Architecture docs, unless asked for a test plan.
- Production features outside the test scope.
- Email adapter or Gmail code.

## Required Inputs

- Tick acceptance criteria.
- Relevant docs and schemas.
- Existing tests.
- Changed implementation files.

## Required Outputs

- Added or updated tests.
- Test command and result.
- Summary of any minimal code changes.

## Done Criteria

- Relevant tests pass.
- Coverage materially improves for the requested behavior.
- No out-of-scope features were introduced.

## Safety Constraints

- Boundary tests must assert absence of Gmail/OpenAI/email sending when relevant.
- Tests must not use real credentials, real recipients, or live email APIs.

