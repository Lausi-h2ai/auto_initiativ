# Reviews

This directory stores Automode tick reviews and audits.

Use one file per tick or phase:

```text
reviews/tick-002-001-review.md
reviews/phase-2-audit.md
```

Each review should include:

- Tick ID.
- Scope reviewed.
- Files inspected.
- Tests run.
- Findings ordered by severity.
- Boundary checks.
- Verdict.
- Required fixes.

Reviewers must prioritize safety, scope control, schema validation, database integrity, auditability, and the agent/program boundary.

