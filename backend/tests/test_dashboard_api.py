from __future__ import annotations

import json

from sqlmodel import Session, select

from backend.app.db import session as db_session_module
from backend.app.db.models import Company, Contact, OutreachRecord, PolicySnapshot, SendIntent
from backend.tests.conftest import copy_valid_run


def _import_valid_run(client, runs_root, run_id: str = "dashboard-valid") -> None:
    copy_valid_run(runs_root, run_id)

    response = client.post(f"/runs/{run_id}/import")

    assert response.status_code == 200
    assert response.json()["run"]["status"] == "imported"


def _import_run_with_blocked_gate_result(client, runs_root) -> None:
    output_path = copy_valid_run(runs_root, "dashboard-blocked-gate")
    gate_path = output_path / "gate_result.json"
    gate_result = json.loads(gate_path.read_text(encoding="utf-8"))
    gate_result.update(
        {
            "gate_result_id": "gate-blocked",
            "status": "blocked",
            "checks": [
                {
                    "code": "blocked_domain",
                    "status": "fail",
                    "details": "Domain is blocked by policy.",
                }
            ],
            "reasons": [
                {
                    "code": "blocked_domain",
                    "message": "Domain is blocked by policy.",
                    "field": "company_domain",
                }
            ],
        }
    )
    gate_path.write_text(json.dumps(gate_result), encoding="utf-8")

    response = client.post("/runs/dashboard-blocked-gate/import")

    assert response.status_code == 200
    assert response.json()["run"]["status"] == "imported"


def _items(response):
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    return body


def _assert_single_match(client, path: str, params: dict[str, object], key: str, value: object) -> None:
    matches = _items(client.get(path, params=params))
    assert len(matches) == 1
    assert matches[0][key] == value


def _assert_no_match(client, path: str, params: dict[str, object]) -> None:
    assert _items(client.get(path, params=params)) == []


def _add_outreach_record() -> OutreachRecord:
    with Session(db_session_module.engine) as session:
        intent = session.exec(select(SendIntent)).one()
        company = session.exec(select(Company)).one()
        contact = session.exec(select(Contact)).one()
        policy = session.exec(select(PolicySnapshot)).one()
        record = OutreachRecord(
            outreach_record_id="outreach-1",
            send_intent_id=intent.id,
            company_id=company.id,
            contact_id=contact.id,
            normalized_recipient_email=intent.normalized_recipient_email,
            company_policy_key=company.company_policy_key,
            policy_snapshot_id=policy.id,
            channel="email",
            status="contacted",
            source="test_fixture",
            notes_json='{"reason": "dashboard read-only fixture"}',
        )
        session.add(record)
        session.commit()
        session.refresh(record)
        return record


def test_dashboard_summary_counts_after_valid_import(client, runs_root):
    _import_valid_run(client, runs_root)

    response = client.get("/dashboard/summary")

    assert response.status_code == 200
    summary = response.json()
    assert summary["companies"] == 1
    assert summary["contacts"] == 1
    assert summary["fit_evaluations"] == 1
    assert summary["email_drafts"] == 1
    assert summary["send_intents"] == 1
    assert summary["gate_results"] == 1
    assert summary["outreach_records"] == 0
    assert summary["send_intents_by_status"] == {"imported": 1}
    assert summary["gate_results_by_status"] == {"passed_evaluate_only": 1}
    assert summary["outreach_records_by_status"] == {}


def test_companies_list_detail_and_filters(client, runs_root):
    _import_valid_run(client, runs_root)

    companies = _items(client.get("/companies"))
    assert len(companies) == 1
    company = companies[0]
    assert company["company_id"] == "company-1"
    assert company["name"] == "Example Robotics"
    assert company["normalized_domain"] == "example.com"
    assert company["source_refs"] == ["source-1"]
    assert company["review_flags"] == []
    assert company["policy_conflicts"][0]["policy_value"] == "none"

    detail = client.get("/companies/company-1")
    assert detail.status_code == 200
    assert detail.json()["company_id"] == "company-1"

    _assert_single_match(client, "/companies", {"min_confidence": 0.9}, "company_id", "company-1")
    _assert_single_match(client, "/companies", {"has_review_flags": False}, "company_id", "company-1")
    _assert_single_match(client, "/companies", {"has_policy_conflicts": True}, "company_id", "company-1")
    _assert_no_match(client, "/companies", {"min_confidence": 0.91})
    _assert_no_match(client, "/companies", {"has_review_flags": True})


def test_contacts_list_detail_and_filters(client, runs_root):
    _import_valid_run(client, runs_root)

    contacts = _items(client.get("/contacts"))
    assert len(contacts) == 1
    contact = contacts[0]
    assert contact["contact_id"] == "contact-1"
    assert contact["external_company_id"] == "company-1"
    assert contact["normalized_recipient_email"] == "alex.hiring@example.com"
    assert contact["email_source"] == "company_site"
    assert contact["source_refs"] == ["source-2"]
    assert contact["review_flags"] == []

    detail = client.get("/contacts/contact-1")
    assert detail.status_code == 200
    assert detail.json()["contact_id"] == "contact-1"

    _assert_single_match(client, "/contacts", {"company_id": "company-1"}, "contact_id", "contact-1")
    _assert_single_match(client, "/contacts", {"email_source": "company_site"}, "contact_id", "contact-1")
    _assert_single_match(client, "/contacts", {"min_confidence": 0.92}, "contact_id", "contact-1")
    _assert_single_match(client, "/contacts", {"has_review_flags": False}, "contact_id", "contact-1")
    _assert_no_match(client, "/contacts", {"company_id": "missing-company"})
    _assert_no_match(client, "/contacts", {"email_source": "inferred_pattern"})


def test_fit_evaluations_list_detail_and_filters(client, runs_root):
    _import_valid_run(client, runs_root)

    evaluations = _items(client.get("/fit-evaluations"))
    assert len(evaluations) == 1
    evaluation = evaluations[0]
    assert evaluation["evaluation_id"] == "evaluation-1"
    assert evaluation["external_company_id"] == "company-1"
    assert evaluation["decision"] == "promising"
    assert evaluation["fit_score"] == 0.81
    assert evaluation["reasons"][0]["text"] == "The company uses Python backend systems."
    assert evaluation["risks"][0]["text"] == "Remote policy needs confirmation."
    assert evaluation["review_flags"] == []

    detail = client.get("/fit-evaluations/evaluation-1")
    assert detail.status_code == 200
    assert detail.json()["evaluation_id"] == "evaluation-1"

    _assert_single_match(client, "/fit-evaluations", {"company_id": "company-1"}, "evaluation_id", "evaluation-1")
    _assert_single_match(client, "/fit-evaluations", {"decision": "promising"}, "evaluation_id", "evaluation-1")
    _assert_single_match(client, "/fit-evaluations", {"min_confidence": 0.82}, "evaluation_id", "evaluation-1")
    _assert_single_match(client, "/fit-evaluations", {"has_review_flags": False}, "evaluation_id", "evaluation-1")
    _assert_no_match(client, "/fit-evaluations", {"decision": "weak_fit"})
    _assert_no_match(client, "/fit-evaluations", {"min_confidence": 0.83})


def test_email_drafts_list_detail_and_filters(client, runs_root):
    _import_valid_run(client, runs_root)

    drafts = _items(client.get("/email-drafts"))
    assert len(drafts) == 1
    draft = drafts[0]
    assert draft["draft_id"] == "draft-1"
    assert draft["external_company_id"] == "company-1"
    assert draft["external_contact_id"] == "contact-1"
    assert draft["subject"] == "Application for backend role"
    assert draft["claim_refs"] == ["claim-1"]
    assert draft["attachments"][0]["attachment_id"] == "attachment-1"
    assert draft["review_flags"] == []

    detail = client.get("/email-drafts/draft-1")
    assert detail.status_code == 200
    assert detail.json()["draft_id"] == "draft-1"

    _assert_single_match(client, "/email-drafts", {"company_id": "company-1"}, "draft_id", "draft-1")
    _assert_single_match(client, "/email-drafts", {"contact_id": "contact-1"}, "draft_id", "draft-1")
    _assert_single_match(client, "/email-drafts", {"min_confidence": 0.88}, "draft_id", "draft-1")
    _assert_single_match(client, "/email-drafts", {"has_review_flags": False}, "draft_id", "draft-1")
    _assert_no_match(client, "/email-drafts", {"contact_id": "missing-contact"})
    _assert_no_match(client, "/email-drafts", {"has_review_flags": True})


def test_send_intents_list_detail_and_filters(client, runs_root):
    _import_valid_run(client, runs_root)

    intents = _items(client.get("/send-intents"))
    assert len(intents) == 1
    intent = intents[0]
    assert intent["intent_id"] == "intent-1"
    assert intent["run_id"] == "dashboard-valid"
    assert intent["external_company_id"] == "company-1"
    assert intent["external_contact_id"] == "contact-1"
    assert intent["external_email_draft_id"] == "draft-1"
    assert intent["normalized_recipient_email"] == "alex.hiring@example.com"
    assert intent["status"] == "imported"
    assert intent["review_flags"] == []

    detail = client.get("/send-intents/intent-1")
    assert detail.status_code == 200
    assert detail.json()["intent_id"] == "intent-1"

    _assert_single_match(client, "/send-intents", {"run_id": "dashboard-valid"}, "intent_id", "intent-1")
    _assert_single_match(client, "/send-intents", {"company_id": "company-1"}, "intent_id", "intent-1")
    _assert_single_match(client, "/send-intents", {"contact_id": "contact-1"}, "intent_id", "intent-1")
    _assert_single_match(client, "/send-intents", {"status": "imported"}, "intent_id", "intent-1")
    _assert_single_match(client, "/send-intents", {"gate_status": "passed_evaluate_only"}, "intent_id", "intent-1")
    _assert_single_match(client, "/send-intents", {"min_confidence": 0.86}, "intent_id", "intent-1")
    _assert_single_match(client, "/send-intents", {"has_review_flags": False}, "intent_id", "intent-1")
    _assert_no_match(client, "/send-intents", {"run_id": "missing-run"})
    _assert_no_match(client, "/send-intents", {"gate_status": "blocked"})


def test_gate_results_list_detail_intent_list_and_filters(client, runs_root):
    _import_run_with_blocked_gate_result(client, runs_root)

    gate_results = _items(client.get("/gate-results"))
    assert len(gate_results) == 1
    gate_result = gate_results[0]
    assert gate_result["gate_result_id"] == "gate-blocked"
    assert gate_result["external_intent_id"] == "intent-1"
    assert gate_result["status"] == "blocked"
    assert gate_result["checks"][0]["code"] == "blocked_domain"
    assert gate_result["reasons"][0]["code"] == "blocked_domain"

    detail = client.get("/gate-results/gate-blocked")
    assert detail.status_code == 200
    assert detail.json()["gate_result_id"] == "gate-blocked"

    intent_results = _items(client.get("/send-intents/intent-1/gate-results"))
    assert [item["gate_result_id"] for item in intent_results] == ["gate-blocked"]

    _assert_single_match(client, "/gate-results", {"intent_id": "intent-1"}, "gate_result_id", "gate-blocked")
    _assert_single_match(client, "/gate-results", {"gate_status": "blocked"}, "gate_result_id", "gate-blocked")
    _assert_single_match(client, "/gate-results", {"reason_code": "blocked_domain"}, "gate_result_id", "gate-blocked")
    _assert_single_match(client, "/send-intents", {"reason_code": "blocked_domain"}, "intent_id", "intent-1")
    _assert_no_match(client, "/gate-results", {"gate_status": "passed_evaluate_only"})
    _assert_no_match(client, "/gate-results", {"reason_code": "missing_sources"})
    _assert_no_match(client, "/send-intents", {"reason_code": "missing_sources"})


def test_outreach_records_list_detail_and_filters_are_read_only(client, runs_root):
    _import_valid_run(client, runs_root)
    _add_outreach_record()

    records = _items(client.get("/outreach-records"))
    assert len(records) == 1
    record = records[0]
    assert record["outreach_record_id"] == "outreach-1"
    assert isinstance(record["send_intent_id"], int)
    assert isinstance(record["company_id"], int)
    assert isinstance(record["contact_id"], int)
    assert record["normalized_recipient_email"] == "alex.hiring@example.com"
    assert record["status"] == "contacted"
    assert record["source"] == "test_fixture"
    assert record["notes"] == {"reason": "dashboard read-only fixture"}

    detail = client.get("/outreach-records/outreach-1")
    assert detail.status_code == 200
    assert detail.json()["outreach_record_id"] == "outreach-1"

    _assert_single_match(client, "/outreach-records", {"company_id": "company-1"}, "outreach_record_id", "outreach-1")
    _assert_single_match(client, "/outreach-records", {"contact_id": "contact-1"}, "outreach_record_id", "outreach-1")
    _assert_single_match(client, "/outreach-records", {"run_id": "dashboard-valid"}, "outreach_record_id", "outreach-1")
    _assert_single_match(client, "/outreach-records", {"status": "contacted"}, "outreach_record_id", "outreach-1")
    _assert_no_match(client, "/outreach-records", {"run_id": "missing-run"})
    _assert_no_match(client, "/outreach-records", {"status": "sent"})

    assert client.post("/outreach-records").status_code in {404, 405}
    assert client.patch("/outreach-records/outreach-1").status_code in {404, 405}


def test_dashboard_does_not_expose_send_or_send_reservation_endpoints(client):
    openapi = client.get("/openapi.json").json()
    paths = {path.lower() for path in openapi["paths"]}

    assert "/send" not in paths
    assert not any(path.endswith("/send") or "/send/" in path for path in paths)
    assert not any("reservation" in path for path in paths)

    assert client.post("/send").status_code == 404
    assert client.get("/send-reservations").status_code == 404
    assert client.get("/dashboard/send-reservations").status_code == 404


def test_audit_logs_support_dashboard_filters(client, runs_root):
    _import_valid_run(client, runs_root)
    copy_valid_run(runs_root, "dashboard-unsupported")
    unsupported_response = client.post("/runs/dashboard-unsupported/import", params={"run_type": "company_research"})
    assert unsupported_response.status_code == 200

    _assert_single_match(
        client,
        "/audit-logs",
        {"run_id": "dashboard-valid", "entity_type": "run", "entity_id": "dashboard-valid", "action": "import_completed"},
        "action",
        "import_completed",
    )
    _assert_single_match(
        client,
        "/audit-logs",
        {"run_id": "dashboard-valid", "result_status": "imported"},
        "result_status",
        "imported",
    )
    _assert_single_match(
        client,
        "/audit-logs",
        {"run_id": "dashboard-unsupported", "reason_code": "unsupported_run_type"},
        "action",
        "import_failed",
    )
    _assert_no_match(client, "/audit-logs", {"run_id": "dashboard-valid", "reason_code": "missing_sources"})
