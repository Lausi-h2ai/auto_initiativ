from __future__ import annotations

import json

import pytest
from sqlmodel import select

from backend.app.db.models import AuditLog, ImportedGateResult, OutreachRecord, SendIntent, SendReservation
from backend.app.gates.evaluate_only import EvaluateOnlyGateService
from backend.app.imports.import_service import RunImportService
from backend.app.schemas.agent_outputs import AGENT_OUTPUT_MODELS
from backend.tests.conftest import copy_valid_run


def _import_valid_run(db_session, runs_root, run_id: str = "gate-valid") -> None:
    copy_valid_run(runs_root, run_id)
    result = RunImportService(db_session).import_run(run_id)
    assert result.run.status == "imported"


def _evaluate(db_session, intent_id: str = "intent-1"):
    result = EvaluateOnlyGateService(db_session).evaluate(intent_id)
    db_session.commit()
    return result


def test_evaluate_only_gate_passes_valid_import_without_reservation(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    result = _evaluate(db_session)

    assert result.gate_result.status == "passed_evaluate_only"
    assert result.gate_result.gate_result_id == "gate-evaluate-only-intent-1"
    assert result.gate_result.imported_file_id is None
    assert not result.reasons
    assert all(check["status"] == "pass" for check in result.checks)
    AGENT_OUTPUT_MODELS["gate_result.schema.json"].model_validate(json.loads(result.gate_result.raw_json))

    assert db_session.exec(select(SendReservation)).all() == []
    audit_actions = [audit.action for audit in db_session.exec(select(AuditLog)).all()]
    assert "gate_evaluation_started" in audit_actions
    assert "gate_evaluation_completed" in audit_actions


def test_evaluate_only_gate_blocks_duplicate_recipient(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    db_session.add(
        OutreachRecord(
            outreach_record_id="outreach-existing",
            normalized_recipient_email="alex.hiring@example.com",
            company_policy_key="domain:other.example",
            status="sent",
        )
    )
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "duplicate_recipient" in {reason["code"] for reason in result.reasons}
    assert db_session.exec(select(SendReservation)).all() == []


def test_evaluate_only_gate_blocks_unapproved_claim_reference(db_session, runs_root):
    _import_valid_run(db_session, runs_root)
    gate_result = db_session.exec(select(ImportedGateResult).where(ImportedGateResult.gate_result_id == "gate-1")).one()
    assert gate_result.imported_file_id is not None
    intent = gate_result.send_intent_id
    assert intent is not None

    send_intent = db_session.get(SendIntent, intent)
    assert send_intent is not None
    send_intent.claim_refs_json = json.dumps(["claim-not-approved"])
    db_session.add(send_intent)
    db_session.commit()

    result = _evaluate(db_session)

    assert result.gate_result.status == "blocked"
    assert "unapproved_claim_refs" in {reason["code"] for reason in result.reasons}


def test_evaluate_only_gate_is_idempotent_for_same_intent(db_session, runs_root):
    _import_valid_run(db_session, runs_root)

    first = _evaluate(db_session)
    second = _evaluate(db_session)

    assert first.gate_result.gate_result_id == second.gate_result.gate_result_id
    generated_results = db_session.exec(
        select(ImportedGateResult).where(ImportedGateResult.gate_result_id == "gate-evaluate-only-intent-1")
    ).all()
    assert len(generated_results) == 1


def test_evaluate_only_gate_api_exposes_gate_result_without_send_endpoint(client, runs_root):
    copy_valid_run(runs_root, "gate-api")
    import_response = client.post("/runs/gate-api/import")
    assert import_response.status_code == 200

    response = client.post("/gate/evaluations/intent-1")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "passed_evaluate_only"
    assert body["gate_result_id"] == "gate-evaluate-only-intent-1"

    openapi = client.get("/openapi.json").json()
    assert "/gate/evaluations/{intent_id}" in openapi["paths"]
    assert not any(path.lower() == "/send" for path in openapi["paths"])


def test_evaluate_only_gate_raises_for_missing_intent(db_session):
    with pytest.raises(ValueError, match="Send intent not found"):
        EvaluateOnlyGateService(db_session).evaluate("missing-intent")
