# Dashboard Scope Plan

Status: `planned`
Date: 2026-05-14
Tick: `AM-004-001`

## Objective

Build a local dashboard that makes backend state inspectable without adding sending behavior. The dashboard must show what agents produced, what the backend imported, what the deterministic gate decided, and why records are blocked or need review.

The dashboard must display backend database state, not agent assumptions.

## MVP Views

1. Runs
   - Show run ID, type, status, output path, timestamps, imported file count, validation status, and audit links.
   - Drill into imported files and validation errors.

2. Companies
   - Show company name, domain, normalized policy key, confidence, review flags, policy conflicts, source refs, and linked fit evaluation status.
   - Filter by confidence, review flags, domain, and policy conflicts.

3. Contacts
   - Show contact name, role, linked company, email source, normalized recipient email, confidence, review flags, and source refs.
   - Filter by company, email source, confidence, and review flags.

4. Fit Evaluations
   - Show company, fit score, decision, reasons, risks, confidence, review flags, and source refs.
   - Filter by decision, score range, confidence, and review flags.

5. Drafts
   - Show subject, body preview, linked company/contact, claim refs, source refs, attachment refs, confidence, and review flags.
   - Keep draft content read-only in the MVP.

6. Send Queue
   - Show imported send intents with recipient, company, subject, linked draft, policy/profile/master-CV IDs, confidence, review flags, and latest gate result.
   - Allow triggering or re-triggering `evaluate_only` gate evaluation only.
   - No reservation, approval, adapter, or send action.

7. Blocked And Needs Review
   - Show intents and gate results filtered by `blocked` or `needs_review`.
   - Surface reason codes, check details, and linked audit entries.

8. Contacted History
   - Show `outreach_records` as read-only historical/contacted state.
   - This is inspection-only; no create/update behavior in the dashboard MVP.

9. Audit Logs
   - Show append-only audit events.
   - Filter by run, entity type, entity ID, action, result status, reason code, and date range.

10. Settings Snapshots
   - Read-only inspection for imported policy, user profile, and master CV snapshots.
   - Surface send limits, blocked domains/names/keywords, review thresholds, and approved claim IDs.

## Primary Workflows

- Inspect a run from import through normalized domain records.
- Understand why a JSON output failed schema validation.
- Review companies, contacts, evaluations, drafts, and send intents by confidence and review flags.
- Inspect a send intent with its linked company, contact, draft, policy snapshot, profile snapshot, master CV snapshot, latest gate result, and audit trail.
- Run deterministic `evaluate_only` for a send intent and inspect persisted checks/reasons.
- Filter the queue by gate status, reason code, confidence, and review flags.
- Confirm no UI path exists for Gmail, adapter handoff, reservation, or sending.

## Current API Surface

Existing endpoints:

- `GET /health`
- `POST /runs/{run_id}/import`
- `GET /runs`
- `GET /runs/{run_id}`
- `GET /runs/{run_id}/files`
- `GET /runs/{run_id}/validation-results`
- `POST /gate/evaluations/{intent_id}`
- `GET /audit-logs`

Existing exposed data covers run import, imported files, validation results, audit logs, and evaluate-only gate execution. It does not yet expose normalized Phase 2 domain records for dashboard browsing.

## API Gaps For Dashboard MVP

Add read-only endpoints before or during dashboard implementation:

- `GET /dashboard/summary`
- `GET /companies`
- `GET /companies/{company_id}`
- `GET /contacts`
- `GET /contacts/{contact_id}`
- `GET /fit-evaluations`
- `GET /fit-evaluations/{evaluation_id}`
- `GET /email-drafts`
- `GET /email-drafts/{draft_id}`
- `GET /send-intents`
- `GET /send-intents/{intent_id}`
- `GET /gate-results`
- `GET /gate-results/{gate_result_id}`
- `GET /send-intents/{intent_id}/gate-results`
- `GET /outreach-records`

Recommended filter support:

- `run_id`
- `company_id`
- `contact_id`
- `status`
- `gate_status`
- `reason_code`
- `action`
- `entity_type`
- `entity_id`
- `decision`
- `email_source`
- `min_confidence`
- `has_review_flags`
- `has_policy_conflicts`
- date range for audit and history records

## AM-004-002 Implementation Scope

Recommended next tick: `AM-004-002A: Add Read-Only Dashboard APIs`

Goal:

- Add read-only API response schemas and endpoints for dashboard data.
- Do not build the frontend until the dashboard API surface exists.

Allowed files:

- `backend/app/api/routes.py`
- `backend/app/schemas/api.py`
- `backend/tests/test_dashboard_api.py`
- `backend/tests/test_boundaries.py` if boundary assertions need updating
- `archive/` and `reviews/` tick artifacts

Acceptance:

- Read-only endpoints exist for companies, contacts, evaluations, drafts, send intents, gate results, outreach records, and summary counts.
- Endpoints support basic filters needed by the MVP.
- Tests cover list/detail/filter behavior.
- Boundary tests continue to prove no `/send`, Gmail, email adapter, reservation creation, or OpenAI dependency.

Recommended following tick: `AM-004-002B: Build Dashboard MVP`

Goal:

- Build a local dashboard UI on top of the read-only APIs.

Allowed scope should be decided after `AM-004-002A`, based on whether the project uses backend-served static HTML or a separate frontend package.

## Out Of Scope

- Gmail integration.
- Email adapter interface or implementation.
- Real sending.
- Send reservations or `reserve_for_send` behavior.
- A `/send` endpoint or UI send button.
- OpenAI API dependency.
- LLM-backed dashboard interpretation.
- Editing source-of-truth records from the dashboard.
- Onboarding workflow implementation.
- Codex run orchestration.
- Marketing landing page.
- New database tables or migrations unless a dashboard API blocker is found.

## Risks And Follow-Ups

- Source and attachment resolution are still represented by imported refs/flags rather than richer records. The dashboard should label this clearly as imported evidence.
- The dashboard must distinguish imported gate-result files from backend-generated evaluate-only gate results.
- `send_reservations` exists as a future-compatible table; surfacing it too early could confuse users. Prefer hiding it until reservations are implemented unless an explicit read-only diagnostic view is needed.
- The dashboard should prioritize blocked/needs-review explanations before any future sending-related UX.
