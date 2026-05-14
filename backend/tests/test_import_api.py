from __future__ import annotations

import json

from backend.tests.conftest import copy_valid_run


def test_health_reports_dry_run_true(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "dry_run": True}


def test_import_and_inspection_endpoints(client, runs_root):
    copy_valid_run(runs_root, "api-valid")

    import_response = client.post("/runs/api-valid/import")

    assert import_response.status_code == 200
    body = import_response.json()
    assert body["run"]["status"] == "imported"
    assert len(body["results"]) == 9

    runs_response = client.get("/runs")
    assert runs_response.status_code == 200
    assert runs_response.json()[0]["run_id"] == "api-valid"

    run_response = client.get("/runs/api-valid")
    assert run_response.status_code == 200
    assert len(run_response.json()["files"]) == 9

    files_response = client.get("/runs/api-valid/files")
    assert files_response.status_code == 200
    assert {item["filename"] for item in files_response.json()} >= {"send_intent.json", "company_candidate.json"}

    validation_response = client.get("/runs/api-valid/validation-results")
    assert validation_response.status_code == 200
    assert all(item["status"] == "schema_validation_passed" for item in validation_response.json())

    audit_response = client.get("/audit-logs", params={"run_id": "api-valid"})
    assert audit_response.status_code == 200
    assert {item["action"] for item in audit_response.json()} >= {"import_started", "import_completed"}


def test_api_exposes_invalid_output_errors(client, runs_root):
    output_path = copy_valid_run(runs_root, "api-invalid")
    contact_path = output_path / "contact_candidate.json"
    contact = json.loads(contact_path.read_text(encoding="utf-8"))
    del contact["email"]
    contact_path.write_text(json.dumps(contact), encoding="utf-8")

    response = client.post("/runs/api-invalid/import")

    assert response.status_code == 200
    assert response.json()["run"]["status"] == "imported_with_errors"

    validation_response = client.get("/runs/api-invalid/validation-results")
    invalid = next(item for item in validation_response.json() if item["filename"] == "contact_candidate.json")
    assert invalid["status"] == "schema_validation_failed"
    assert "missing_required_field" in invalid["reason_codes"]
    assert invalid["errors"][0]["path"] == "$"


def test_api_reports_unsupported_run_type_as_failed_import(client, runs_root):
    copy_valid_run(runs_root, "api-unsupported-type")

    response = client.post("/runs/api-unsupported-type/import", params={"run_type": "company_research"})

    assert response.status_code == 200
    body = response.json()
    assert body["run"]["status"] == "import_failed"
    assert body["run"]["agent_type"] == "company_research"
    assert body["results"] == []

    audit_response = client.get("/audit-logs", params={"run_id": "api-unsupported-type"})
    failure = next(item for item in audit_response.json() if item["action"] == "import_failed")
    assert failure["reason_codes"] == ["unsupported_run_type"]
    assert failure["metadata"]["run_type"] == "company_research"


def test_no_send_endpoint_exists(client):
    response = client.post("/send")
    assert response.status_code == 404

    openapi = client.get("/openapi.json").json()
    assert not any(path.lower() == "/send" for path in openapi["paths"])
