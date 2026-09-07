# Contributing

Start with the [README](README.md) for setup and [AGENTS.md](AGENTS.md) for repository constraints. Keep changes focused and describe the problem, resulting behavior, and validation in each pull request.

## Checks

```sh
uv sync --locked --python 3.12 --extra test
npm ci
uv run pytest --basetemp artifacts/pytest-temp
npm run typecheck
npm run build
uv tool run ruff==0.16.6 check backend
git diff --check
```

Use `npm.cmd` on Windows if PowerShell blocks the npm script. Use a distinct workspace-local pytest temp directory for concurrent runs. The backend serves built assets from `backend/app/static/app/`; edit React source and rebuild rather than editing generated bundles.

For PostgreSQL integration tests, create a disposable database, set `POSTGRES_TEST_DATABASE_URL` to its SQLAlchemy URL, and run:

```sh
uv run pytest backend/tests/test_postgres_dedupe_constraints.py backend/tests/test_postgres_workflow_claims.py --basetemp artifacts/pytest-postgres
```

These tests apply migrations and insert records. Never point them at a personal or production database. SQLite tests do not establish PostgreSQL locking behavior.

Live browser tests under `tests/` require a separately running app. Use fictional data and a disposable workspace; never publish screenshots or traces from a personal account. `tests/document-library-live.spec.js` requires a seeded fictional workspace for candidate `Alex Morgan`: 251 documents total (124 tailored CVs, 124 emails, and three profile documents), with 24 visible cards per page. It also requires a `Northstar Labs` company with exactly one tailored CV and one email; the tailored CV PDF must contain `Alex Morgan`.

## Design boundaries

- Agents produce candidate files; deterministic application code owns state, authorization, policy, dedupe, and side effects.
- Validate agent JSON against its schema before importing it. Ground personal claims in the approved master CV.
- Preserve the privileged email gate, reservation, and audit sequence.
- Read the relevant architecture decision and migration plan before changing workflow authority or replacing agent responsibilities.
- Include regression tests for changed behavior. Keep third-party source and license notices intact.

## Before sharing

Follow [SECURITY.md](SECURITY.md). A clean working tree does not mean the Git history is free of sensitive data. Public fixtures must be fictional, with reserved example domains. Do not attach `.env`, databases, CVs, run directories, or raw logs to issues.
