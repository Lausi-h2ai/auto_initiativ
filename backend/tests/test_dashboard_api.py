from __future__ import annotations

import json

from sqlmodel import Session, select

from backend.app.db import session as db_session_module
from backend.app.db.models import (
    Company,
    Contact,
    EmailDraft,
    FitEvaluation,
    ImportedGateResult,
    OutreachRecord,
    PolicySnapshot,
    SendIntent,
    UserProfileSnapshot,
)
from backend.app.imports.import_service import RunImportService
from backend.app.onboarding.promotion import OnboardingPromotionService, SnapshotPromotionRequest
from backend.tests.conftest import FIXTURES_ROOT, copy_valid_run


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


def _approve_profile_snapshots(db_session, runs_root, run_id: str = "campaign-approved") -> None:
    output_path = runs_root / run_id / "output"
    output_path.mkdir(parents=True, exist_ok=True)
    fixture_output = FIXTURES_ROOT / "valid_run" / "output"
    for filename in ("user_profile.json", "master_cv_profile.json", "policy.json", "onboarding_review.json"):
        (output_path / filename).write_text((fixture_output / filename).read_text(encoding="utf-8"), encoding="utf-8")
    result = RunImportService(db_session).import_run(run_id, run_type="onboarding_chat")
    assert result.run.status == "imported"
    promoted = OnboardingPromotionService(db_session).promote_run_snapshots(
        run_id,
        SnapshotPromotionRequest(
            reviewer_id="test-reviewer",
            confirm_user_profile=True,
            confirm_master_cv_profile=True,
            confirm_policy=True,
        ),
    )
    db_session.commit()
    assert promoted.status == "approved"


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


def _add_company_contact(db_session, *, company_id: str = "company-application") -> tuple[Company, Contact]:
    company = Company(
        company_id=company_id,
        name="Application Robotics",
        raw_domain="application.example",
        normalized_domain="application.example",
        normalized_name="application robotics",
        company_policy_key="domain:application.example",
        company_policy_key_kind="domain",
        description="Robotics software company.",
        industry_tags_json='["robotics"]',
        locations_json='["Zurich"]',
        remote_policy="hybrid",
        source_refs_json='["https://application.example"]',
        confidence=0.9,
        review_flags_json="[]",
        policy_conflicts_json="[]",
        raw_json=json.dumps(
            {
                "schema_version": "1.0",
                "company_id": company_id,
                "name": "Application Robotics",
                "domain": "application.example",
                "description": "Robotics software company.",
                "industry_tags": ["robotics"],
                "locations": ["Zurich"],
                "remote_policy": "hybrid",
                "source_refs": ["https://application.example"],
                "confidence": 0.9,
                "review_flags": [],
            }
        ),
    )
    db_session.add(company)
    db_session.flush()
    contact = Contact(
        contact_id=f"{company_id}-careers",
        company_id=company.id,
        external_company_id=company_id,
        role_title="Careers team",
        raw_email="careers@application.example",
        normalized_recipient_email="careers@application.example",
        email_source="company_site",
        source_refs_json='["https://application.example/careers"]',
        confidence=0.88,
        review_flags_json="[]",
        raw_json=json.dumps(
            {
                "schema_version": "1.0",
                "contact_id": f"{company_id}-careers",
                "company_id": company_id,
                "role_title": "Careers team",
                "email": "careers@application.example",
                "email_source": "company_site",
                "source_refs": ["https://application.example/careers"],
                "confidence": 0.88,
                "review_flags": [],
            }
        ),
    )
    db_session.add(contact)
    db_session.commit()
    db_session.refresh(company)
    db_session.refresh(contact)
    return company, contact


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


def test_queue_email_draft_creates_send_intent_and_gate_result(client, runs_root):
    _import_valid_run(client, runs_root, "queue-draft")
    attachment_path = runs_root / "queue-draft" / "output" / "attachments" / "cv.pdf"
    attachment_path.parent.mkdir(parents=True, exist_ok=True)
    attachment_path.write_bytes(b"%PDF-1.4\n% test cv\n")
    with Session(db_session_module.engine) as session:
        promoted = OnboardingPromotionService(session).promote_run_snapshots(
            "queue-draft",
            SnapshotPromotionRequest(
                reviewer_id="test-reviewer",
                confirm_user_profile=True,
                confirm_master_cv_profile=True,
                confirm_policy=True,
            ),
        )
        assert promoted.status == "approved"
        for gate_result in session.exec(select(ImportedGateResult)).all():
            session.delete(gate_result)
        for send_intent in session.exec(select(SendIntent)).all():
            session.delete(send_intent)
        session.commit()

    response = client.post("/email-drafts/draft-1/queue-send", json={"reviewer_id": "test-reviewer"})

    assert response.status_code == 200
    body = response.json()
    assert body["created"] is True
    assert body["send_intent"]["intent_id"] == "intent-draft-1"
    assert body["send_intent"]["external_email_draft_id"] == "draft-1"
    assert body["send_intent"]["attachments"][0]["exists_at_draft_time"] is True
    assert body["gate_result"]["status"] == "passed_evaluate_only"

    queue_response = client.get("/send-intents")
    assert queue_response.status_code == 200
    queued = queue_response.json()
    assert len(queued) == 1
    assert queued[0]["intent_id"] == "intent-draft-1"
    drafts_response = client.get("/email-drafts")
    assert drafts_response.status_code == 200
    drafts = drafts_response.json()
    assert len(drafts) == 1
    assert drafts[0]["queued_send_intent_id"] == "intent-draft-1"
    assert drafts[0]["queued_gate_status"] == "passed_evaluate_only"

    second_response = client.post("/email-drafts/draft-1/queue-send", json={"reviewer_id": "test-reviewer"})
    assert second_response.status_code == 200
    assert second_response.json()["created"] is False


def test_company_research_campaign_prepare_requires_approved_profile(client):
    response = client.post("/campaigns/company-research", json={"run_id": "campaign-no-profile"})

    assert response.status_code == 409
    assert "approved user profile" in response.json()["detail"]


def test_company_research_campaign_prepare_and_imports_company_fit(client, db_session, runs_root):
    _approve_profile_snapshots(db_session, runs_root)
    existing_company, _ = _add_company_contact(db_session, company_id="already-known-company")
    approved_profile = db_session.exec(select(UserProfileSnapshot).where(UserProfileSnapshot.status == "approved")).one()
    approved_policy = db_session.exec(select(PolicySnapshot).where(PolicySnapshot.status == "approved")).one()
    db_session.add(
        FitEvaluation(
            evaluation_id="already-known-company-fit",
            company_id=existing_company.id,
            external_company_id=existing_company.company_id,
            user_profile_snapshot_id=approved_profile.id,
            policy_snapshot_id=approved_policy.id,
            fit_score=0.8,
            decision="promising",
            reasons_json='[{"text":"Known for this user profile.","source_refs":["test"]}]',
            risks_json="[]",
            source_refs_json='["test"]',
            confidence=0.8,
            review_flags_json="[]",
            raw_json=json.dumps(
                {
                    "schema_version": "1.0",
                    "evaluation_id": "already-known-company-fit",
                    "company_id": existing_company.company_id,
                    "profile_id": approved_profile.profile_id,
                    "policy_id": approved_policy.policy_id,
                    "fit_score": 0.8,
                    "decision": "promising",
                    "reasons": [{"text": "Known for this user profile.", "source_refs": ["test"]}],
                    "risks": [],
                    "source_refs": ["test"],
                    "confidence": 0.8,
                    "review_flags": [],
                }
            ),
        )
    )
    other_company, _ = _add_company_contact(db_session, company_id="other-profile-company")
    db_session.add(
        FitEvaluation(
            evaluation_id="other-profile-company-fit",
            company_id=other_company.id,
            external_company_id=other_company.company_id,
            user_profile_snapshot_id=None,
            policy_snapshot_id=approved_policy.id,
            fit_score=0.8,
            decision="promising",
            reasons_json='[{"text":"Known for a different profile.","source_refs":["test"]}]',
            risks_json="[]",
            source_refs_json='["test"]',
            confidence=0.8,
            review_flags_json="[]",
            raw_json="{}",
        )
    )
    db_session.commit()

    prepared = client.post(
        "/campaigns/company-research",
        json={
            "run_id": "campaign-one",
            "role_focus": "Backend platform roles",
            "time_budget_minutes": 15,
            "max_companies": 24,
        },
    )

    assert prepared.status_code == 200
    payload = prepared.json()
    assert payload["status"] == "prepared"
    assert payload["expected_output_files"] == ["companies/*.json", "contacts/*.json", "fit_evaluations/*.json"]
    assert (runs_root / "campaign-one" / "input" / "user_profile.json").exists()
    assert (runs_root / "campaign-one" / "input" / "schemas" / "contact_candidate.schema.json").exists()
    campaign = json.loads((runs_root / "campaign-one" / "input" / "campaign.json").read_text(encoding="utf-8"))
    existing_companies = json.loads((runs_root / "campaign-one" / "input" / "existing_companies.json").read_text(encoding="utf-8"))
    assert campaign["time_budget_minutes"] == 15
    assert campaign["locations"] == ["Berlin"]
    assert campaign["max_companies"] == 24
    assert existing_companies["companies"][0]["company_id"] == existing_company.company_id
    assert existing_companies["companies"][0]["name"] == "Application Robotics"
    assert existing_companies["companies"][0]["domain"] == "application.example"
    assert existing_companies["companies"][0]["profile_id"] == approved_profile.profile_id
    assert {company["company_id"] for company in existing_companies["companies"]} == {existing_company.company_id}
    assert "company_research" in (runs_root / "campaign-one" / "manifest.json").read_text(encoding="utf-8")

    fixture_output = FIXTURES_ROOT / "valid_run" / "output"
    output_path = runs_root / "campaign-one" / "output"
    (output_path / "companies").mkdir()
    (output_path / "fit_evaluations").mkdir()
    company = json.loads((fixture_output / "company_candidate.json").read_text(encoding="utf-8"))
    company.update({"company_id": "company-campaign-1", "name": "Campaign Robotics", "domain": "campaign.example"})
    fit = json.loads((fixture_output / "fit_evaluation.json").read_text(encoding="utf-8"))
    fit.update({"evaluation_id": "evaluation-campaign-1", "company_id": "company-campaign-1"})
    (output_path / "companies" / "campaign-robotics.json").write_text(json.dumps(company), encoding="utf-8")
    (output_path / "fit_evaluations" / "campaign-robotics-fit.json").write_text(json.dumps(fit), encoding="utf-8")

    imported = client.post("/runs/campaign-one/import", params={"run_type": "company_research"})

    assert imported.status_code == 200
    assert imported.json()["run"]["status"] == "imported"
    campaign_company = db_session.exec(select(Company).where(Company.company_id == "company-campaign-1")).one()
    campaign_fit = db_session.exec(select(FitEvaluation).where(FitEvaluation.evaluation_id == "evaluation-campaign-1")).one()
    assert campaign_fit.company_id == campaign_company.id
    assert campaign_fit.user_profile_snapshot_id is not None
    assert campaign_fit.policy_snapshot_id is not None


def test_company_research_reimport_of_existing_stable_ids_does_not_mark_run_error(client, db_session, runs_root):
    _approve_profile_snapshots(db_session, runs_root)
    fixture_output = FIXTURES_ROOT / "valid_run" / "output"

    for run_id in ("campaign-duplicate-source", "campaign-duplicate-repeat"):
        prepared = client.post("/campaigns/company-research", json={"run_id": run_id})
        assert prepared.status_code == 200
        output_path = runs_root / run_id / "output"
        (output_path / "companies").mkdir()
        (output_path / "fit_evaluations").mkdir()
        company = json.loads((fixture_output / "company_candidate.json").read_text(encoding="utf-8"))
        company.update({"company_id": "company-repeat", "domain": "repeat.example"})
        fit = json.loads((fixture_output / "fit_evaluation.json").read_text(encoding="utf-8"))
        fit.update({"evaluation_id": "company-repeat-fit", "company_id": "company-repeat"})
        (output_path / "companies" / "repeat.json").write_text(json.dumps(company), encoding="utf-8")
        (output_path / "fit_evaluations" / "repeat-fit.json").write_text(json.dumps(fit), encoding="utf-8")

    first = client.post("/runs/campaign-duplicate-source/import", params={"run_type": "company_research"})
    second = client.post("/runs/campaign-duplicate-repeat/import", params={"run_type": "company_research"})

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["run"]["status"] == "imported"
    assert second.json()["run"]["status"] == "imported"
    assert len(db_session.exec(select(Company).where(Company.company_id == "company-repeat")).all()) == 1
    assert len(db_session.exec(select(FitEvaluation).where(FitEvaluation.evaluation_id == "company-repeat-fit")).all()) == 1


def test_company_research_batch_import_keeps_valid_records_when_one_file_fails(client, db_session, runs_root):
    _approve_profile_snapshots(db_session, runs_root)
    prepared = client.post("/campaigns/company-research", json={"run_id": "campaign-partial"})
    assert prepared.status_code == 200

    fixture_output = FIXTURES_ROOT / "valid_run" / "output"
    output_path = runs_root / "campaign-partial" / "output"
    (output_path / "companies").mkdir()
    (output_path / "fit_evaluations").mkdir()
    company = json.loads((fixture_output / "company_candidate.json").read_text(encoding="utf-8"))
    company.update({"company_id": "company-partial-1", "name": "Partial Valid", "domain": "partial.example"})
    invalid_company = dict(company)
    invalid_company.pop("source_refs")
    fit = json.loads((fixture_output / "fit_evaluation.json").read_text(encoding="utf-8"))
    fit.update({"evaluation_id": "evaluation-partial-1", "company_id": "company-partial-1"})
    (output_path / "companies" / "valid.json").write_text(json.dumps(company), encoding="utf-8")
    (output_path / "companies" / "invalid.json").write_text(json.dumps(invalid_company), encoding="utf-8")
    (output_path / "fit_evaluations" / "valid-fit.json").write_text(json.dumps(fit), encoding="utf-8")

    imported = client.post("/runs/campaign-partial/import", params={"run_type": "company_research"})

    assert imported.status_code == 200
    body = imported.json()
    assert body["run"]["status"] == "imported_with_errors"
    assert any(result["filename"] == "companies/invalid.json" and result["status"] == "schema_validation_failed" for result in body["results"])
    campaign_company = db_session.exec(select(Company).where(Company.company_id == "company-partial-1")).one()
    campaign_fit = db_session.exec(select(FitEvaluation).where(FitEvaluation.evaluation_id == "evaluation-partial-1")).one()
    assert campaign_fit.company_id == campaign_company.id


def test_company_research_launch_and_status_endpoints_use_runtime(client, monkeypatch):
    from backend.app.api.routes import get_company_research_runtime

    class FakeRuntime:
        def launch(self, run_id):
            class Result:
                run_id = "campaign-one"
                status = "running"
                command = ["pi", "--mode", "rpc"]
                workdir = "runs/campaign-one/workspace"

            return Result()

        def status(self, run_id):
            return {
                "run_id": run_id,
                "runtime": "pi_rpc",
                "status": "running",
                "state": {"status": "running"},
                "artifact_counts": {"companies": 1, "contacts": 1, "fit_evaluations": 1},
                "validation": {"result_count": 0, "passed": 0, "failed": 0, "files": []},
                "import_state": {"run_status": "research_running", "imported_file_count": 0},
                "logs": [{"type": "pi_rpc_started"}],
            }

    client.app.dependency_overrides[get_company_research_runtime] = lambda: FakeRuntime()

    launched = client.post("/campaigns/company-research/campaign-one/launch")
    status = client.get("/campaigns/company-research/campaign-one/status")

    assert launched.status_code == 200
    assert launched.json()["status_endpoint"] == "/campaigns/company-research/campaign-one/status"
    assert status.status_code == 200
    assert status.json()["artifact_counts"] == {"companies": 1, "contacts": 1, "fit_evaluations": 1}


def test_application_draft_prepare_import_and_attachment_review_endpoint(client, db_session, runs_root, tmp_path, monkeypatch):
    from backend.app.core.config import get_settings

    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    for filename in (
        "initiativbewerbung-style-guide.md",
        "initiativbewerbung-workflow.md",
        "resume-job-search-context.md",
    ):
        (handoff_dir / filename).write_text(f"# {filename}\nUse concise sourced drafts.\n", encoding="utf-8")
    master_cv = tmp_path / "de_ch_master.html"
    master_cv.write_text("<html><body><main>Master CV</main></body></html>", encoding="utf-8")
    monkeypatch.setenv("APPLICATION_DRAFT_HANDOFF_DIR", str(handoff_dir))
    monkeypatch.setenv("APPLICATION_DRAFT_MASTER_CV_HTML_PATH", str(master_cv))
    get_settings.cache_clear()

    _approve_profile_snapshots(db_session, runs_root)
    company, contact = _add_company_contact(db_session)

    prepared = client.post(
        "/application-drafts",
        json={"run_id": "application-one", "company_id": company.company_id},
    )

    assert prepared.status_code == 200
    payload = prepared.json()
    assert payload["status"] == "prepared"
    assert payload["company_id"] == company.company_id
    assert payload["contact_id"] == contact.contact_id
    assert payload["expected_output_files"] == ["email_draft.json"]
    assert (runs_root / "application-one" / "input" / "draft_context.json").exists()
    assert not (runs_root / "application-one" / "input" / "handoff" / "initiativbewerbung-style-guide.md").exists()
    assert (runs_root / "application-one" / "input" / "master_cv" / "de_ch_master.html").exists()

    output_path = runs_root / "application-one" / "output"
    attachments_path = output_path / "attachments"
    attachments_path.mkdir(exist_ok=True)
    (attachments_path / "application-robotics-lebenslauf.pdf").write_bytes(b"%PDF-" + (b"0" * 10_000))
    (attachments_path / "application-robotics-lebenslauf.html").write_text(
        "<html><head><style>@page { size: A4; margin: 10mm; }</style></head><body>Tailored CV</body></html>",
        encoding="utf-8",
    )
    (output_path / "email_draft.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "draft_id": payload["draft_id"],
                "company_id": company.company_id,
                "contact_id": contact.contact_id,
                "subject": "Initiativbewerbung",
                "body_text": "Guten Tag, anbei mein Lebenslauf.",
                "tone": "professional",
                "claim_refs": ["claim-1"],
                "source_refs": ["https://application.example"],
                "attachments": [
                    {
                        "attachment_id": "cv-application-robotics",
                        "path": "attachments/application-robotics-lebenslauf.pdf",
                        "kind": "cv",
                    }
                ],
                "confidence": 0.84,
                "review_flags": [],
            }
        ),
        encoding="utf-8",
    )

    imported = client.post("/application-drafts/application-one/import")

    assert imported.status_code == 200
    assert imported.json()["import_result"]["run"]["status"] == "imported"
    drafts = client.get("/email-drafts", params={"run_id": "application-one"})
    assert drafts.status_code == 200
    assert drafts.json()[0]["draft_id"] == payload["draft_id"]

    attachment = client.get(f"/application-drafts/{payload['draft_id']}/attachments/cv-application-robotics")
    assert attachment.status_code == 200
    assert attachment.headers["content-type"] == "application/pdf"
    assert attachment.content.startswith(b"%PDF")


def test_application_draft_prepare_rejects_missing_contact_by_default(client, db_session, runs_root, tmp_path, monkeypatch):
    from backend.app.core.config import get_settings

    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    for filename in (
        "initiativbewerbung-style-guide.md",
        "initiativbewerbung-workflow.md",
        "resume-job-search-context.md",
    ):
        (handoff_dir / filename).write_text("# guide\n", encoding="utf-8")
    master_cv = tmp_path / "de_ch_master.html"
    master_cv.write_text("<html>CV</html>", encoding="utf-8")
    monkeypatch.setenv("APPLICATION_DRAFT_HANDOFF_DIR", str(handoff_dir))
    monkeypatch.setenv("APPLICATION_DRAFT_MASTER_CV_HTML_PATH", str(master_cv))
    get_settings.cache_clear()

    _approve_profile_snapshots(db_session, runs_root)
    company = Company(
        company_id="company-no-contact",
        name="No Contact AG",
        normalized_name="no contact ag",
        company_policy_key="name:no contact ag",
        company_policy_key_kind="name",
        source_refs_json='["https://no-contact.example"]',
        confidence=0.8,
        review_flags_json="[]",
        policy_conflicts_json="[]",
        raw_json=json.dumps(
            {
                "schema_version": "1.0",
                "company_id": "company-no-contact",
                "name": "No Contact AG",
                "source_refs": ["https://no-contact.example"],
                "confidence": 0.8,
                "review_flags": [],
            }
        ),
    )
    db_session.add(company)
    db_session.commit()

    response = client.post("/application-drafts", json={"run_id": "application-no-contact", "company_id": "company-no-contact"})

    assert response.status_code == 409
    assert "imported contact" in response.json()["detail"]
    assert not (runs_root / "application-no-contact").exists()


def test_application_draft_batch_selected_prepares_and_bounded_launches(client, db_session, runs_root, tmp_path, monkeypatch):
    from backend.app.core.config import get_settings
    import backend.app.api.routes as routes

    handoff_dir = tmp_path / "handoff"
    handoff_dir.mkdir()
    for filename in (
        "initiativbewerbung-style-guide.md",
        "initiativbewerbung-workflow.md",
        "resume-job-search-context.md",
    ):
        (handoff_dir / filename).write_text("# guide\n", encoding="utf-8")
    master_cv = tmp_path / "de_ch_master.html"
    master_cv.write_text("<html>CV</html>", encoding="utf-8")
    monkeypatch.setenv("APPLICATION_DRAFT_HANDOFF_DIR", str(handoff_dir))
    monkeypatch.setenv("APPLICATION_DRAFT_MASTER_CV_HTML_PATH", str(master_cv))
    get_settings.cache_clear()

    _approve_profile_snapshots(db_session, runs_root)
    approved_profile = db_session.exec(select(UserProfileSnapshot).where(UserProfileSnapshot.status == "approved")).one()
    approved_policy = db_session.exec(select(PolicySnapshot).where(PolicySnapshot.status == "approved")).one()
    eligible_company, _ = _add_company_contact(db_session, company_id="batch-eligible")
    no_contact_company, no_contact = _add_company_contact(db_session, company_id="batch-needs-contact-research")
    db_session.delete(no_contact)
    out_of_scope_company, _ = _add_company_contact(db_session, company_id="batch-out-of-scope")
    for company, profile_id in ((eligible_company, approved_profile.id), (out_of_scope_company, None)):
        db_session.add(
            FitEvaluation(
                evaluation_id=f"{company.company_id}-fit",
                company_id=company.id,
                external_company_id=company.company_id,
                user_profile_snapshot_id=profile_id,
                policy_snapshot_id=approved_policy.id,
                fit_score=0.8,
                decision="promising",
                reasons_json='[{"text":"Relevant.","source_refs":["test"]}]',
                risks_json="[]",
                source_refs_json='["test"]',
                confidence=0.8,
                review_flags_json="[]",
                raw_json="{}",
            )
        )
    db_session.add(
        FitEvaluation(
            evaluation_id=f"{no_contact_company.company_id}-fit",
            company_id=no_contact_company.id,
            external_company_id=no_contact_company.company_id,
            user_profile_snapshot_id=approved_profile.id,
            policy_snapshot_id=approved_policy.id,
            fit_score=0.8,
            decision="promising",
            reasons_json='[{"text":"Relevant.","source_refs":["test"]}]',
            risks_json="[]",
            source_refs_json='["test"]',
            confidence=0.8,
            review_flags_json="[]",
            raw_json="{}",
        )
    )
    db_session.commit()

    launched: list[str] = []

    class FakeBatchRuntime:
        def __init__(self, *, settings=None):
            self.settings = settings

        def launch(self, run_id):
            launched.append(run_id)

        def status(self, run_id):
            return {"status": "imported"}

    monkeypatch.setattr(routes, "ApplicationDraftRuntime", FakeBatchRuntime)

    response = client.post(
        "/application-drafts/batches",
        json={
            "mode": "selected",
            "company_ids": ["batch-eligible", "batch-needs-contact-research", "batch-out-of-scope"],
            "concurrency": 1,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["requested_count"] == 3
    by_company = {item["company_id"]: item for item in body["items"]}
    assert by_company["batch-eligible"]["status"] in {"queued", "launched", "running", "completed"}
    assert by_company["batch-eligible"]["run_id"].startswith("application-draft-application-robotics-")
    assert by_company["batch-needs-contact-research"]["status"] == "skipped"
    assert by_company["batch-needs-contact-research"]["reason"] == "needs_contact"
    assert by_company["batch-out-of-scope"]["status"] in {"queued", "launched", "running", "completed"}
    assert by_company["batch-out-of-scope"]["reason"] is None
    assert (runs_root / by_company["batch-eligible"]["run_id"] / "input" / "application_draft.json").exists()
    assert by_company["batch-needs-contact-research"].get("run_id") is None


def test_companies_list_detail_and_filters(client, db_session, runs_root):
    _import_valid_run(client, runs_root)
    company_1 = db_session.exec(select(Company).where(Company.company_id == "company-1")).one()
    db_session.add(
        OutreachRecord(
            outreach_record_id="outreach-company-1",
            company_id=company_1.id,
            normalized_recipient_email="alex.hiring@example.com",
            company_policy_key=company_1.company_policy_key,
            channel="email",
            status="sent",
            dedupe_recipient=True,
            dedupe_company=True,
            source="test",
        )
    )
    db_session.add(
        Company(
            company_id="company-undrafted",
            name="Undrafted Company",
            raw_domain="undrafted.example",
            normalized_domain="undrafted.example",
            normalized_name="undrafted company",
            company_policy_key="domain:undrafted.example",
            company_policy_key_kind="domain",
            description="Company without an application draft.",
            industry_tags_json="[]",
            locations_json="[]",
            remote_policy="unknown",
            source_refs_json='["source-undrafted"]',
            confidence=0.8,
            review_flags_json='["needs_review"]',
            policy_conflicts_json="[]",
            raw_json='{"company_id":"company-undrafted"}',
        )
    )
    db_session.commit()

    companies = _items(client.get("/companies"))
    assert len(companies) == 2
    company = next(item for item in companies if item["company_id"] == "company-1")
    assert company["company_id"] == "company-1"
    assert company["name"] == "Example Robotics"
    assert company["normalized_domain"] == "example.com"
    assert company["source_refs"] == ["source-1"]
    assert company["review_flags"] == []
    assert company["policy_conflicts"][0]["policy_value"] == "none"
    assert company["has_application_draft"] is True
    assert company["has_send_intent"] is True
    assert company["send_intent_status"] == "imported"
    assert company["send_gate_status"] == "passed_evaluate_only"
    assert company["has_been_contacted"] is True
    assert company["outreach_status"] == "sent"
    assert company["fit_score"] == 0.81
    assert company["fit_decision"] == "promising"
    assert company["fit_reasons"]
    undrafted = next(item for item in companies if item["company_id"] == "company-undrafted")
    assert undrafted["has_application_draft"] is False
    assert undrafted["has_send_intent"] is False
    assert undrafted["has_been_contacted"] is False
    assert undrafted["can_draft_application"] is True
    assert undrafted["application_draft_block_reason"] is None

    detail = client.get("/companies/company-1")
    assert detail.status_code == 200
    assert detail.json()["company_id"] == "company-1"
    assert detail.json()["has_application_draft"] is True
    assert detail.json()["has_been_contacted"] is True

    _assert_single_match(client, "/companies", {"min_confidence": 0.9}, "company_id", "company-1")
    _assert_single_match(client, "/companies", {"has_review_flags": False}, "company_id", "company-1")
    _assert_single_match(client, "/companies", {"has_policy_conflicts": True}, "company_id", "company-1")
    _assert_single_match(client, "/companies", {"draft_status": "drafted"}, "company_id", "company-1")
    _assert_single_match(client, "/companies", {"draft_status": "missing"}, "company_id", "company-undrafted")
    _assert_no_match(client, "/companies", {"min_confidence": 0.91})
    _assert_single_match(client, "/companies", {"has_review_flags": True}, "company_id", "company-undrafted")


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


def test_outbox_drafts_returns_simple_completed_draft_rows(client, runs_root):
    output = copy_valid_run(runs_root, "outbox-drafts")
    attachments = output / "attachments"
    attachments.mkdir(exist_ok=True)
    (attachments / "cv.pdf").write_bytes(b"%PDF-1.4\nfake cv\n")
    response = client.post("/runs/outbox-drafts/import")
    assert response.status_code == 200

    rows = _items(client.get("/outbox/drafts"))

    assert len(rows) == 1
    row = rows[0]
    assert row["company_name"] == "Example Robotics"
    assert row["email_address"] == "alex.hiring@example.com"
    assert row["status"] == "ready"
    assert row["status_label"] == "Ready"
    assert row["email_url"] == "/email-drafts/draft-1"
    assert row["cv"]["url"] == "/application-drafts/draft-1/attachments/attachment-1"
    assert "review_flags" not in row
    assert "claim_refs" not in row


def test_outbox_drafts_uses_only_narrow_blocker_labels(client, runs_root):
    output = copy_valid_run(runs_root, "outbox-blockers")
    attachments = output / "attachments"
    attachments.mkdir(exist_ok=True)
    (attachments / "cv.pdf").write_bytes(b"%PDF-1.4\nfake cv\n")
    response = client.post("/runs/outbox-blockers/import")
    assert response.status_code == 200
    with Session(db_session_module.engine) as session:
        session.exec(select(EmailDraft)).one()
        contact = session.exec(select(Contact)).one()
        contact.raw_email = ""
        session.add(contact)
        session.commit()

    rows = _items(client.get("/outbox/drafts"))

    assert rows[0]["status"] == "blocked"
    assert rows[0]["status_label"] == "Missing email"
    assert rows[0]["blocker_code"] == "missing_email"


def test_outbox_send_all_queues_ready_drafts_through_backend_send_flow(client, db_session, runs_root):
    output = copy_valid_run(runs_root, "outbox-send-all")
    attachments = output / "attachments"
    attachments.mkdir(exist_ok=True)
    (attachments / "cv.pdf").write_bytes(b"%PDF-1.4\nfake cv\n")
    response = client.post("/runs/outbox-send-all/import")
    assert response.status_code == 200
    promoted = OnboardingPromotionService(db_session).promote_run_snapshots(
        "outbox-send-all",
        SnapshotPromotionRequest(
            reviewer_id="test-reviewer",
            confirm_user_profile=True,
            confirm_master_cv_profile=True,
            confirm_policy=True,
        ),
    )
    assert promoted.status == "approved"
    for gate_result in db_session.exec(select(ImportedGateResult)).all():
        db_session.delete(gate_result)
    for send_intent in db_session.exec(select(SendIntent)).all():
        db_session.delete(send_intent)
    db_session.commit()

    result = client.post("/outbox/send-all", json={"reviewer_id": "local-user"})

    assert result.status_code == 200
    body = result.json()
    assert body["requested_count"] == 1
    assert body["sent_count"] == 0
    assert body["blocked_count"] == 1
    assert body["batch"]["items"][0]["status"] == "send_disabled"
    assert body["drafts"][0]["status"] == "ready"


def test_outbox_send_all_blocks_already_contacted_company(client, db_session, runs_root):
    output = copy_valid_run(runs_root, "outbox-dedupe")
    attachments = output / "attachments"
    attachments.mkdir(exist_ok=True)
    (attachments / "cv.pdf").write_bytes(b"%PDF-1.4\nfake cv\n")
    response = client.post("/runs/outbox-dedupe/import")
    assert response.status_code == 200
    _add_outreach_record()

    rows = _items(client.get("/outbox/drafts"))
    result = client.post("/outbox/send-all", json={"reviewer_id": "local-user"})

    assert rows[0]["status_label"] == "Already contacted"
    assert result.status_code == 200
    assert result.json()["requested_count"] == 0
    assert result.json()["sent_count"] == 0


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
    unsupported_response = client.post("/runs/dashboard-unsupported/import", params={"run_type": "unsupported_research"})
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
