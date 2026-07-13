# Backend Instructions

- Use FastAPI for HTTP APIs, Postgres for durable state, SQLModel or SQLAlchemy for persistence, and Pydantic at import and API boundaries.
- Keep safety, dedupe, policy, limits, and gates deterministic and independent from any LLM.
- Do not add an OpenAI API dependency unless the user explicitly requests a task that requires it.
- Validate every code-consumed agent JSON output against its governing schema before import.
- After backend, configuration, dependency, or served-static changes, restart the FastAPI app and verify `/health` and `/dashboard` as required by the root instructions.

## Windows Tests

Always give pytest a workspace-local temp root because the default per-user directory may be inaccessible:

```powershell
.\.venv\Scripts\python.exe -m pytest --basetemp artifacts\pytest-temp
```

Use a distinct `artifacts\pytest-temp-*` path for concurrent runs. After a default `%TEMP%\pytest-of-*` permission error, retry with a workspace-local path rather than the default location.
