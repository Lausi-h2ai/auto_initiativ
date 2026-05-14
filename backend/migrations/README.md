# Backend Migrations

Alembic migrations for the backend live here.

The migration strategy is documented in `adr/0001-migration-strategy.md`.

Use migrations for durable databases:

```powershell
uv run --python 3.12 alembic upgrade head
```

Fast unit tests may still use SQLite and `SQLModel.metadata.create_all()` when they do not depend on Postgres-specific behavior. Constraint and migration integration tests should use Postgres.

