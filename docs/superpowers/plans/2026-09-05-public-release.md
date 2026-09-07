# Public Release Implementation Plan

**Goal:** Make the repository understandable to recruiters and prepare a reviewed public snapshot without personal data or credentials.

**Architecture:** Preserve application behavior and deterministic safety boundaries. Improve repository documentation, safe setup examples, and publication checks; audit reachable Git history separately from the working tree.

**Tech stack:** FastAPI, SQLModel, React, TypeScript, pytest, Git.

**Spec:** Repository owner's request for code cleanup, an intuitive README, and removal of secrets and PII before pushing.

## Constraints

- Preserve local credentials, databases, run folders, and unrelated files.
- Do not send email or push changes.
- No application schemas or API boundaries change in this stage.
- Keep vendored source and its license intact.
- Commit relevant paths if the environment permits Git metadata writes.

## Tasks

- [ ] Audit tracked files, reachable historical blobs, commit metadata, and binary artifacts. Report locations and categories without credential values.
- [x] Replace the README with a product overview, workflow diagram, setup, engineering highlights, and clear limitations. Add contribution and security guidance, a safe environment example, and broader private-artifact ignores. Fresh-checkout verification remains outstanding.
- [ ] Replace personal test/documentation values with fictional examples, normalize package manifest formatting, and run backend tests and TypeScript checks.
- [ ] Add automated checks for the public source tree and CI for the existing test suite, including disposable PostgreSQL tests.
- [ ] Verify publication inputs and prepare historical cleanup without deleting private local data. Commit reviewed paths if permitted; report any remaining publication blocker explicitly.

Progress and concrete environment blockers are recorded in [PUBLIC_RELEASE.md](../../PUBLIC_RELEASE.md).
