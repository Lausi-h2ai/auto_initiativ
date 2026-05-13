# Codex Workflow

## Run Folder Contract

Each Codex task should run in an isolated folder:

```text
runs/<run_id>/
  input/
  output/
  logs/
  task.md
  instructions.md
```

## Backend Preparation

The backend creates:

- `task.md` with the specific goal.
- `instructions.md` with boundary rules and output requirements.
- `input/` files with only the context required for the task.

The backend should avoid giving an agent secrets, email credentials, or direct send capabilities.

## Agent Execution

Codex reads `task.md`, `instructions.md`, and files under `input/`.

Codex writes:

- Structured JSON to `output/`.
- Optional markdown notes to `logs/`.
- No database mutations.
- No emails.

## Import

The backend imports `output/` files by:

1. Reading expected files for the run type.
2. Validating against `schemas/`.
3. Resolving source references.
4. Storing normalized records.
5. Writing audit logs.
6. Reporting validation failures to the dashboard.

## Recommended Run Types

- `onboarding`
- `company_research`
- `contact_research`
- `fit_evaluation`
- `cv_tailoring`
- `email_drafting`
- `send_intent`

## Instructions Template Requirements

Every run instruction should include:

- The agent's allowed output files.
- The schema path for each output file.
- A reminder that Codex must not send email.
- A reminder to mark uncertainty.
- A reminder that backend validation is authoritative.

