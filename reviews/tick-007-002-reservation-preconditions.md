# Tick 007-002 Review: Reservation Preconditions

## Scope

Reviewed `AM-007-002: Reservation Preconditions`.

## Result

Pass.

The implementation adds `ReserveForSendGateService`, a private backend service that:

- Runs the existing deterministic gate checks.
- Creates a `SendReservation` only when the evaluation passes.
- Updates the gate result to `reserved_for_send` with `external_reservation_id`.
- Blocks active recipient/company reservation conflicts.
- Does not commit by itself, expose a route, invoke the fake adapter, create outreach records, or send email.

Additional handoff tests cover missing reservation id, missing reservation row, inactive reservation, intent/policy/company mismatch, reserved gate results with reasons, and spoofed fake-provider adapters.

## Review Fixes

A reviewer found two issues before closure:

- Adapter provider strings were spoofable. Fixed by requiring the concrete `FakeDryRunEmailAdapter` type during this phase.
- Existing reservation reuse did not verify company and dedupe fields. Fixed and covered with stale-reservation regression tests.

## Verification

Ran:

```powershell
uv run --python 3.12 --extra test pytest backend/tests/test_reserve_for_send_gate.py backend/tests/test_email_adapter_handoff.py backend/tests/test_import_api.py::test_no_send_endpoint_exists backend/tests/test_boundaries.py -q
```

Result: `28 passed`.

Ran full suite:

```powershell
uv run --python 3.12 --extra test pytest -q --basetemp=.tmp\pytest-tick-007-002
```

Result: `210 passed, 1 skipped`.

## Residual Risk

The service is intentionally private. There is still no public approval or reservation endpoint, no real provider adapter, and no send-result/outreach persistence for actual sending.
