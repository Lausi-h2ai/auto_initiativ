# AM-003-003 Gate Test Matrix

Status: `implemented`
Date: 2026-05-14

## Scope

This matrix covers deterministic `evaluate_only` gate behavior. It does not cover `reserve_for_send`, reservations, adapter handoff, Gmail, OpenAI usage, or sending.

## Covered Reasons And Checks

| Area | Focused coverage |
| --- | --- |
| Happy path | Valid imported intent returns `passed_evaluate_only`; no reservation is created. |
| Schema validity | Missing raw JSON, missing required field, additional property, invalid enum, and invalid email format block. |
| Required records | Missing company, contact, email draft, user profile snapshot, master CV snapshot, policy snapshot, and policy mismatch block. |
| Dedupe | Duplicate contacted recipient and duplicate contacted company block; policy-allowed repeats pass. |
| Policy exclusions | Blocked domain, blocked company name, and blocked keyword block. |
| Sources | Missing source refs and refs absent from the linked draft block. |
| Attachments | Attachment marked missing at draft time blocks. |
| Limits | Missing limits, daily limit reached, and weekly limit reached block. |
| Claims | Unapproved claim refs and forbidden claim text block. |
| Confidence | Low confidence on send intent, company, contact, email draft, and fit evaluation blocks. Missing confidence threshold blocks. |
| Review flags | Required-record review flags block when policy requires blocking; send-intent review flags produce `needs_review` when policy allows review. |
| Contact safety | Inferred contact email source produces `needs_review`; unknown source blocks. |
| Status precedence | Combined failure and warning returns `blocked`. |
| Audit and determinism | Completed audit reason codes match gate reasons; repeated evaluation of the same snapshot is idempotent. |
| API boundary | Gate evaluation endpoint returns evidence; `/send` remains absent. |

## Intentional Deferrals

- Actual attachment filesystem or attachment-record resolution remains future work. Current gate behavior follows the imported `exists_at_draft_time` field.
- Richer source registry resolution remains future work. AM-003-003 tightened unresolved draft source refs from warning to block.
- Contact safety is still driven by deterministic `email_source` classes rather than a broader policy object for private/personal/weak-source cases.

## Verification

```powershell
uv run --python 3.12 --extra test pytest backend/tests/test_evaluate_only_gate.py -q --basetemp=.tmp\pytest-gate-matrix
```

Result: 43 passed.
