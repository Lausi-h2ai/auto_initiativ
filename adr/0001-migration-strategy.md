# ADR-0001: Migration Strategy

## Status

Accepted

## Context

Phase 1 uses SQLModel for operational persistence and has four tables:

- `runs`
- `imported_files`
- `validation_results`
- `audit_logs`

Phase 2 will add normalized source-of-truth domain tables and database-enforced dedupe constraints. Those constraints will rely on Postgres behavior such as partial unique indexes and JSON-capable storage. The project needs migration history before adding those tables.

The user has made these decisions for Tick AM-002-002:

- Use SQLModel if Phase 1 already uses SQLModel.
- Use Alembic now.
- Keep SQLite support only for fast unit tests where possible.
- Use Postgres for constraint and migration integration tests.
- Do not support SQLite as an equal production backend.
- Avoid destructive migrations.

## Decision

Use Alembic as the migration tool starting in Phase 2.

Keep SQLModel as the ORM/model layer for now. Alembic `env.py` will load `SQLModel.metadata` after importing the backend models so autogenerate can see the current schema.

Use `DATABASE_URL` from application settings for Alembic instead of relying on a hardcoded production URL in `alembic.ini`.

Add an initial migration that creates the existing Phase 1 operational tables for fresh databases. This migration is additive and non-destructive.

For existing local databases that were created with `SQLModel.metadata.create_all()`, use `alembic stamp head` after confirming the schema matches. Do not run destructive migrations to force local state into shape.

## Consequences

- Phase 2 model changes must include Alembic migrations.
- SQLModel remains the model source unless a later ADR changes that.
- Fast unit tests may keep using SQLite where they do not depend on Postgres-specific behavior.
- Migration and constraint integration tests should use Postgres.
- Partial unique indexes, JSON behavior, and future reservation constraints must be verified against Postgres before relying on them.
- `SQLModel.metadata.create_all()` remains acceptable for isolated fast tests, but not as the production migration path.

## Migration Workflow

For a fresh local database:

```powershell
uv run --python 3.12 alembic upgrade head
```

For an existing local database already created by Phase 1:

```powershell
uv run --python 3.12 alembic current
uv run --python 3.12 alembic stamp head
```

For new model changes:

```powershell
uv run --python 3.12 alembic revision --autogenerate -m "short description"
uv run --python 3.12 alembic upgrade head
uv run --python 3.12 --extra test pytest
```

Every generated migration must be reviewed before use. Do not accept destructive operations, table drops, or column drops unless the user explicitly approves the data-loss risk.

The initial Phase 1 migration intentionally disables destructive downgrade. Future migrations should follow the same default: prefer forward fixes and explicit data-preserving migrations over rollback scripts that drop source-of-truth data.

## Test Policy

Use SQLite only for fast tests that verify application logic independent of database-specific behavior.

Use Postgres-backed tests for:

- Migrations.
- Partial unique indexes.
- JSON/JSONB assumptions.
- Concurrency-sensitive reservation or dedupe constraints.
- Any behavior that must match production-like persistence.

If Postgres is not available in a local test environment, Postgres integration tests should skip with a clear reason rather than silently passing on SQLite.

## Alternatives Considered

### Continue With `create_all()` Only

Rejected. It is too weak for Phase 2 because dedupe constraints and future reservations need explicit migration history.

### Switch To Plain SQLAlchemy Declarative Now

Rejected for now. Phase 1 already uses SQLModel successfully, and switching ORM style during migration setup would add unnecessary scope.

### Treat SQLite As A Production-Equivalent Backend

Rejected. SQLite is useful for fast local tests, but it is not equivalent for Postgres partial indexes, JSON behavior, and future transaction semantics.
