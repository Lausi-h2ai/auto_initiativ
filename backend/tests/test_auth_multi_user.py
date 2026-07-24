from __future__ import annotations

import json
from collections.abc import Generator
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from backend.app.auth.context import RequestIdentity, scoped_runs_root, workspace_context
from backend.app.auth.service import AuthService, GoogleIdentity, csrf_token
from backend.app.core.config import get_settings
from backend.app.db.models import (
    AdminAccessAudit,
    AgentTask,
    AuditLog,
    Campaign,
    CampaignCompany,
    CampaignJob,
    Company,
    Contact,
    Document,
    EmailDraft,
    ImportedFile,
    Invitation,
    JobFitEvaluation,
    JobPosting,
    MasterCvProfileSnapshot,
    PolicySnapshot,
    ReviewException,
    User,
    UserProfileSnapshot,
    Workspace,
    utc_now,
)


@pytest.fixture()
def authenticated_app(tmp_path, monkeypatch: pytest.MonkeyPatch) -> Generator[dict[str, object], None, None]:
    database_url = f"sqlite:///{tmp_path / 'auth.db'}"
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("RUNS_ROOT", str(tmp_path / "runs"))
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv("BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_ID", "test-client")
    monkeypatch.setenv("GOOGLE_OAUTH_CLIENT_SECRET", "test-secret")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "test-encryption-key")
    monkeypatch.setenv("EMAIL_SENDING_ENABLED", "false")
    monkeypatch.setenv("WORKFLOW_WORKER_ENABLED", "false")
    monkeypatch.setenv("ISSUE_LOG_PATH", str(tmp_path / "issues.ndjson"))
    get_settings.cache_clear()

    from backend.app.db import session as session_module
    from backend.app.main import create_app

    session_module.engine = session_module.build_engine(database_url)
    SQLModel.metadata.create_all(session_module.engine)
    settings = get_settings()
    with Session(session_module.engine) as session:
        auth = AuthService(session, settings)
        admin = auth.authenticate_google_identity(
            GoogleIdentity("google-admin", "admin@example.com", True, "Admin User")
        )
        admin_token = auth.create_session(admin)
        session.add(
            Invitation(
                invitation_id="invitation-user",
                email="user@example.com",
                invited_by_user_id=admin.id,
            )
        )
        session.commit()
        user = auth.authenticate_google_identity(
            GoogleIdentity("google-user", "user@example.com", True, "Candidate User")
        )
        user_token = auth.create_session(user)
        admin_workspace = session.exec(select(Workspace).where(Workspace.owner_user_id == admin.id)).one()
        user_workspace = session.exec(select(Workspace).where(Workspace.owner_user_id == user.id)).one()

        for identity, name in (
            (RequestIdentity(admin.id, admin_workspace.id, "admin"), "Admin Company"),
            (RequestIdentity(user.id, user_workspace.id, "user"), "User Company"),
        ):
            with workspace_context(identity):
                session.add(
                    Company(
                        company_id="company-shared",
                        name=name,
                        normalized_name=name.lower().replace(" ", "-"),
                        company_policy_key="domain:shared.example",
                        company_policy_key_kind="domain",
                        confidence=0.9,
                        raw_json=json.dumps({"name": name}),
                    )
                )
                session.add(
                    UserProfileSnapshot(
                        profile_id="profile-shared",
                        schema_version="1.0.0",
                        content_hash=f"profile-{identity.user_id}",
                        status="approved",
                        raw_json="{}",
                    )
                )
                session.add(
                    MasterCvProfileSnapshot(
                        profile_id="master-cv-shared",
                        schema_version="1.0.0",
                        content_hash=f"master-{identity.user_id}",
                        status="approved",
                        raw_json="{}",
                    )
                )
                session.add(
                    PolicySnapshot(
                        policy_id="policy-shared",
                        schema_version="1.0.0",
                        content_hash=f"policy-{identity.user_id}",
                        status="approved",
                        raw_json="{}",
                    )
                )
                session.commit()

        admin_workspace_id = admin_workspace.id
        admin_workspace_public_id = admin_workspace.workspace_id
        user_workspace_id = user_workspace.id
        user_workspace_public_id = user_workspace.workspace_id
        user_id = user.id

    with TestClient(create_app()) as client:
        yield {
            "client": client,
            "engine": session_module.engine,
            "settings": settings,
            "admin_token": admin_token,
            "user_token": user_token,
            "admin_workspace_id": admin_workspace_id,
            "admin_workspace_public_id": admin_workspace_public_id,
            "user_workspace_id": user_workspace_id,
            "user_workspace_public_id": user_workspace_public_id,
            "user_id": user_id,
        }


def test_unauthenticated_api_is_rejected(authenticated_app):
    response = authenticated_app["client"].get("/companies", follow_redirects=False)
    assert response.status_code == 401


def test_local_registration_lists_and_switches_fresh_workspaces(client, db_session):
    legacy_user = User(
        google_subject="bootstrap:legacy",
        email="legacy@local.invalid",
        display_name="Legacy administrator",
        status="pending",
        role="admin",
    )
    db_session.add(legacy_user)
    db_session.flush()
    db_session.add(Workspace(workspace_id="workspace-legacy", owner_user_id=legacy_user.id, name="Legacy workspace"))
    db_session.commit()
    capabilities = client.get("/auth/local/capabilities")
    assert capabilities.status_code == 200
    assert capabilities.json() == {"registration_enabled": True}
    assert client.get("/register").status_code == 200

    first = client.post(
        "/auth/local/register",
        json={"display_name": "Fresh One", "email": "fresh-one@example.com"},
    )
    assert first.status_code == 201
    first_me = client.get("/me")
    assert first_me.status_code == 200
    assert first_me.json()["email"] == "fresh-one@example.com"
    assert first_me.json()["workspace"]["id"].startswith("workspace-local-")
    assert first_me.json()["local_registration_enabled"] is True
    assert client.get("/product/summary").json()["pipeline"] == {}

    second = client.post(
        "/auth/local/register",
        json={"display_name": "Fresh Two", "email": "fresh-two@example.com"},
    )
    assert second.status_code == 201
    second_me = client.get("/me").json()
    assert second_me["id"] != first_me.json()["id"]
    assert second_me["workspace"]["id"] != first_me.json()["workspace"]["id"]
    assert second_me["email"] == "fresh-two@example.com"
    assert client.get("/product/summary").json()["pipeline"] == {}

    accounts = client.get("/auth/local/accounts")
    assert accounts.status_code == 200
    account_rows = {item["email"]: item for item in accounts.json()}
    assert account_rows["legacy@local.invalid"]["workspace"]["name"] == "Legacy workspace"
    assert account_rows["fresh-two@example.com"]["is_current"] is True
    assert account_rows["fresh-one@example.com"]["is_current"] is False
    assert account_rows["fresh-one@example.com"]["workspace"]["id"] == first_me.json()["workspace"]["id"]

    switched_back = client.post("/auth/local/switch", json={"user_id": first_me.json()["id"]})
    assert switched_back.status_code == 200
    assert client.get("/me").json()["id"] == first_me.json()["id"]

    legacy = client.post("/auth/local/switch", json={"user_id": account_rows["legacy@local.invalid"]["id"]})
    assert legacy.status_code == 200
    assert client.get("/me").json()["workspace"]["name"] == "Legacy workspace"


def test_local_registration_is_disabled_in_authenticated_mode(authenticated_app):
    response = authenticated_app["client"].post(
        "/auth/local/register",
        json={"display_name": "Not Allowed", "email": "blocked@example.com"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Local account access is disabled when authentication is required."
    assert authenticated_app["client"].get("/auth/local/accounts").status_code == 403
    assert authenticated_app["client"].post("/auth/local/switch", json={"user_id": authenticated_app["user_id"]}).status_code == 403


def test_workspace_queries_and_duplicate_ids_are_isolated(authenticated_app):
    client = authenticated_app["client"]
    admin = client.get("/companies", cookies={"ai_session": authenticated_app["admin_token"]})
    user = client.get("/companies", cookies={"ai_session": authenticated_app["user_token"]})

    assert admin.status_code == 200
    assert user.status_code == 200
    assert [item["name"] for item in admin.json()] == ["Admin Company"]
    assert [item["name"] for item in user.json()] == ["User Company"]


def test_approved_profile_bundle_is_workspace_isolated(authenticated_app):
    client = authenticated_app["client"]
    admin = client.get("/profile/approved", cookies={"ai_session": authenticated_app["admin_token"]})
    user = client.get("/profile/approved", cookies={"ai_session": authenticated_app["user_token"]})

    assert admin.status_code == 200
    assert user.status_code == 200
    assert admin.json()["user_profile"]["snapshot"]["id"] != user.json()["user_profile"]["snapshot"]["id"]


def test_admin_can_inspect_other_workspace_read_only_and_access_is_audited(authenticated_app):
    client = authenticated_app["client"]
    target = authenticated_app["user_workspace_public_id"]
    headers = {"X-Workspace-Id": target}
    cookies = {"ai_session": authenticated_app["admin_token"]}

    response = client.get("/companies", headers=headers, cookies=cookies)
    assert response.status_code == 200
    assert [item["name"] for item in response.json()] == ["User Company"]

    csrf = csrf_token(authenticated_app["admin_token"], authenticated_app["settings"])
    mutation = client.post(
        "/campaigns/company-research",
        headers={**headers, "X-CSRF-Token": csrf},
        cookies=cookies,
        json={},
    )
    assert mutation.status_code == 403

    with Session(authenticated_app["engine"]) as session:
        audit = session.exec(select(AdminAccessAudit)).all()
    assert len(audit) == 1
    assert audit[0].target_workspace_id == authenticated_app["user_workspace_id"]


def test_invite_endpoint_requires_admin_and_csrf(authenticated_app):
    client = authenticated_app["client"]
    user_token = authenticated_app["user_token"]
    user_csrf = csrf_token(user_token, authenticated_app["settings"])
    denied = client.post(
        "/admin/invitations",
        cookies={"ai_session": user_token},
        headers={"X-CSRF-Token": user_csrf},
        json={"email": "new@example.com"},
    )
    assert denied.status_code == 403

    admin_token = authenticated_app["admin_token"]
    created = client.post(
        "/admin/invitations",
        cookies={"ai_session": admin_token},
        headers={"X-CSRF-Token": csrf_token(admin_token, authenticated_app["settings"])},
        json={"email": "new@example.com"},
    )
    assert created.status_code == 201
    assert created.json()["status"] == "pending"


def test_google_identity_must_be_invited(authenticated_app):
    with Session(authenticated_app["engine"]) as session:
        with pytest.raises(Exception) as error:
            AuthService(session, authenticated_app["settings"]).authenticate_google_identity(
                GoogleIdentity("uninvited", "stranger@example.com", True, "Stranger")
            )
    assert getattr(error.value, "status_code", None) == 403


def test_unlinked_legacy_companies_are_visible_in_product_summary(authenticated_app):
    response = authenticated_app["client"].get(
        "/product/summary",
        cookies={"ai_session": authenticated_app["user_token"]},
    )

    assert response.status_code == 200
    assert response.json()["pipeline"] == {"discovered": 1}


def test_legacy_drafts_and_profiles_are_exposed_as_safe_workspace_documents(authenticated_app):
    identity = RequestIdentity(
        user_id=authenticated_app["user_id"],
        workspace_id=authenticated_app["user_workspace_id"],
    )
    with workspace_context(identity), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.company_id == "company-shared")).one()
        imported_file = ImportedFile(
            run_id="application-draft-library",
            path="output/email_draft.json",
            filename="email_draft.json",
            status="imported",
            raw_json="{}",
        )
        session.add(imported_file)
        session.flush()
        cv_path = (
            scoped_runs_root(authenticated_app["settings"].runs_root)
            / imported_file.run_id
            / "output"
            / "attachments"
            / "user-company-cv.pdf"
        )
        cv_path.parent.mkdir(parents=True, exist_ok=True)
        cv_path.write_bytes(b"%PDF-1.4\n% tailored test CV\n")
        cv_path.with_suffix(".html").write_text(
            '<html><body><img src="file:///private/photo.jpg"><h1>Tailored User CV</h1></body></html>',
            encoding="utf-8",
        )
        session.add(
            EmailDraft(
                draft_id="draft-library",
                company_id=company.id,
                external_company_id=company.company_id,
                external_contact_id="contact-library",
                subject="Applied AI engineer",
                body_text="Hello <script>alert('no')</script>",
                confidence=0.91,
                raw_json="{}",
                imported_file_id=imported_file.id,
            )
        )
        session.commit()

    client = authenticated_app["client"]
    cookies = {"ai_session": authenticated_app["user_token"]}
    response = client.get("/documents", cookies=cookies)

    assert response.status_code == 200
    documents = response.json()
    assert len(documents) == 5
    assert {item["type"] for item in documents} == {
        "email_draft",
        "tailored_cv",
        "career_profile",
        "master_cv_profile",
        "outreach_policy",
    }
    email = next(item for item in documents if item["type"] == "email_draft")
    assert email["title"] == "User Company — Applied AI engineer"

    preview = client.get(email["preview_url"], cookies=cookies)
    assert preview.status_code == 200
    assert "<script>" not in preview.text
    assert "&lt;script&gt;" in preview.text
    assert preview.headers["content-security-policy"].startswith("default-src 'none'")

    cv = next(item for item in documents if item["type"] == "tailored_cv")
    assert cv["title"] == "User Company — Tailored CV"
    cv_preview = client.get(cv["preview_url"], cookies=cookies)
    assert cv_preview.status_code == 200
    assert cv_preview.headers["content-type"].startswith("text/html")
    assert "Tailored User CV" in cv_preview.text
    assert "file:///private/photo.jpg" not in cv_preview.text
    assert "data:image/gif;base64" in cv_preview.text
    assert cv_preview.headers["content-security-policy"].startswith("default-src 'none'")
    cv_download = client.get(cv["download_url"], cookies=cookies)
    assert cv_download.status_code == 200
    assert cv_download.headers["content-type"].startswith("application/pdf")

    profile = next(item for item in documents if item["type"] == "career_profile")
    profile_preview = client.get(profile["preview_url"], cookies=cookies)
    assert profile_preview.status_code == 200
    assert profile_preview.headers["content-type"].startswith("text/html")
    assert "Approved source of truth" in profile_preview.text
    assert profile_preview.headers["content-security-policy"].startswith("default-src 'none'")

    summary = client.get("/product/summary", cookies=cookies)
    assert summary.json()["document_count"] == 5

    admin_documents = client.get(
        "/documents",
        cookies={"ai_session": authenticated_app["admin_token"]},
    ).json()
    assert len(admin_documents) == 3
    assert all(item["type"] != "email_draft" for item in admin_documents)
    assert all(item["type"] != "tailored_cv" for item in admin_documents)


def test_application_documents_index_only_logical_pdfs_without_cv_alias_duplication(authenticated_app):
    from backend.app.workflow.engine import WorkflowEngine

    identity = RequestIdentity(
        user_id=authenticated_app["user_id"],
        workspace_id=authenticated_app["user_workspace_id"],
    )
    run_id = "application-draft-logical-documents"
    with workspace_context(identity), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.company_id == "company-shared")).one()
        campaign = Campaign(
            campaign_id="campaign-logical-documents",
            name="Logical application documents",
            campaign_type="initiative_outreach",
            status="preparing",
        )
        session.add(campaign)
        session.flush()
        task = AgentTask(
            task_id="task-logical-documents",
            campaign_id=campaign.id,
            company_id=company.id,
            run_id=run_id,
            agent_role="resume_and_email_team",
            task_type="application_draft",
            status="running",
        )
        session.add(task)
        session.flush()
        output = scoped_runs_root(authenticated_app["settings"].runs_root) / run_id / "output"
        attachments = output / "attachments"
        attachments.mkdir(parents=True)
        (attachments / "company-lebenslauf.pdf").write_bytes(b"%PDF-1.4\n% cv\n")
        (attachments / "company-anschreiben.pdf").write_bytes(b"%PDF-1.4\n% cover\n")
        (attachments / "debug-preview.pdf").write_bytes(b"%PDF-1.4\n% debug\n")
        (attachments / "company-lebenslauf.html").write_text("<html>CV source</html>", encoding="utf-8")
        (attachments / "company-anschreiben.html").write_text("<html>Letter source</html>", encoding="utf-8")
        (output / "email_draft.json").write_text("{}", encoding="utf-8")

        WorkflowEngine(session, authenticated_app["settings"])._index_documents(task, company)
        imported_file = ImportedFile(
            run_id=run_id,
            path="output/email_draft.json",
            filename="email_draft.json",
            status="imported",
            raw_json="{}",
        )
        session.add(imported_file)
        session.flush()
        draft = EmailDraft(
            draft_id="draft-logical-documents",
            company_id=company.id,
            external_company_id=company.company_id,
            external_contact_id="contact-logical-documents",
            subject="Logical documents",
            body_text="Hello",
            confidence=0.9,
            raw_json="{}",
            imported_file_id=imported_file.id,
        )
        session.add(draft)
        session.commit()
        draft_id = draft.id

        indexed = session.exec(select(Document).where(Document.run_id == run_id)).all()
        assert {item.filename for item in indexed} == {"company-lebenslauf.pdf", "company-anschreiben.pdf"}
        assert {item.document_type for item in indexed} == {"tailored_cv", "cover_letter"}
        assert next(item for item in indexed if item.document_type == "cover_letter").title.endswith("Cover letter")

    client = authenticated_app["client"]
    cookies = {"ai_session": authenticated_app["user_token"]}
    documents = client.get("/documents", cookies=cookies).json()
    run_documents = [item for item in documents if item.get("filename", "").startswith("company-") or item["id"] == f"email-draft-{draft_id}"]
    assert len(run_documents) == 3
    assert [item["type"] for item in run_documents].count("tailored_cv") == 1
    assert [item["type"] for item in run_documents].count("cover_letter") == 1
    assert [item["type"] for item in run_documents].count("email_draft") == 1

    legacy_alias = client.get(f"/documents/tailored-cv-{draft_id}/download", cookies=cookies)
    assert legacy_alias.status_code == 200
    assert legacy_alias.content == b"%PDF-1.4\n% cv\n"


def test_campaign_creation_is_on_rails_and_requires_plan_confirmation(authenticated_app):
    client = authenticated_app["client"]
    token = authenticated_app["user_token"]
    headers = {"X-CSRF-Token": csrf_token(token, authenticated_app["settings"])}
    response = client.post(
        "/campaigns",
        cookies={"ai_session": token},
        headers=headers,
        json={
            "name": "Swiss applied AI",
            "role_focus": "Machine learning engineering",
            "locations": ["Zurich", "Remote Switzerland"],
            "max_companies": 25,
            "sending_mode": "prepare_only",
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "planning"
    assert response.json()["research_plan_status"] == "pending_confirmation"
    assert response.json()["active_task_count"] == 0
    assert [item["label"] for item in response.json()["research_plan"]["targets"]] == ["Zurich", "Remote Switzerland"]

    confirmed = client.post(
        f"/campaigns/{response.json()['id']}/research-plan/confirm",
        cookies={"ai_session": token},
        headers=headers,
    )
    assert confirmed.status_code == 202
    assert confirmed.json()["status"] == "researching"
    assert confirmed.json()["active_task_count"] == 2

    summary = client.get("/product/summary", cookies={"ai_session": token})
    assert summary.status_code == 200
    assert summary.json()["active_campaign"]["name"] == "Swiss applied AI"
    assert summary.json()["active_tasks"][0]["agent_role"] == "company_researcher"

    gated = client.patch(
        f"/campaigns/{response.json()['id']}/sending-mode",
        cookies={"ai_session": token},
        headers=headers,
        json={"sending_mode": "gated_autosend"},
    )
    assert gated.status_code == 409
    assert "Connect Gmail" in gated.json()["detail"]


def test_listed_job_campaign_is_separate_and_manual_submit_only(authenticated_app):
    client = authenticated_app["client"]
    token = authenticated_app["user_token"]
    headers = {"X-CSRF-Token": csrf_token(token, authenticated_app["settings"])}
    response = client.post(
        "/campaigns",
        cookies={"ai_session": token},
        headers=headers,
        json={
            "campaign_type": "listed_job_search",
            "name": "Verified AI roles",
            "role_focus": "",
            "locations": ["Zurich"],
            "max_jobs": 20,
            "freshness_days": 30,
            "sending_mode": "prepare_only",
        },
    )
    assert response.status_code == 201
    assert response.json()["campaign_type"] == "listed_job_search"
    assert response.json()["brief"]["role_focus"] == "Profile-aligned roles"
    assert response.json()["job_count"] == 0
    assert response.json()["status"] == "planning"
    assert response.json()["research_plan_status"] == "pending_confirmation"
    assert response.json()["active_task_count"] == 0

    confirmed = client.post(
        f"/campaigns/{response.json()['id']}/research-plan/confirm",
        cookies={"ai_session": token},
        headers=headers,
    )
    assert confirmed.status_code == 202
    assert confirmed.json()["active_task_count"] == 1

    blocked = client.patch(
        f"/campaigns/{response.json()['id']}/sending-mode",
        cookies={"ai_session": token},
        headers=headers,
        json={"sending_mode": "gated_autosend"},
    )
    assert blocked.status_code == 422

    refresh = client.post(
        f"/campaigns/{response.json()['id']}/refresh",
        cookies={"ai_session": token},
        headers=headers,
    )
    assert refresh.status_code == 409
    assert refresh.json()["detail"] == "Balanced target research is still active; wait for it to finish before refreshing."


def test_verified_job_queues_tailored_application_agent(authenticated_app):
    client = authenticated_app["client"]
    token = authenticated_app["user_token"]
    headers = {"X-CSRF-Token": csrf_token(token, authenticated_app["settings"])}
    with workspace_context(RequestIdentity(user_id=authenticated_app["user_id"], workspace_id=authenticated_app["user_workspace_id"])), Session(authenticated_app["engine"]) as session:
        profile = session.exec(select(UserProfileSnapshot).where(UserProfileSnapshot.status == "approved")).first()
        master = session.exec(select(MasterCvProfileSnapshot).where(MasterCvProfileSnapshot.status == "approved")).first()
        profile.imported_at = utc_now() - timedelta(days=121)
        master.imported_at = utc_now() - timedelta(days=121)
        session.add_all([profile, master])
        policy = session.exec(select(PolicySnapshot).where(PolicySnapshot.status == "approved")).first()
        company = session.exec(select(Company).where(Company.name == "User Company")).one()
        campaign = Campaign(campaign_id="campaign-job-package", name="Open roles", campaign_type="listed_job_search", status="active", sending_mode="prepare_only", user_profile_snapshot_id=profile.id, master_cv_profile_snapshot_id=master.id, policy_snapshot_id=policy.id)
        session.add(campaign)
        session.flush()
        job = JobPosting(job_id="job-package-test", company_id=company.id, external_company_id=company.company_id, title="Applied AI Engineer", source_url="https://example.com/jobs/1", canonical_url="https://example.com/jobs/1", application_url="https://example.com/jobs/1/apply", source_domain="example.com", source_kind="employer", fingerprint="package-test", vacancy_status="verified_open", date_posted=utc_now(), last_verified_at=utc_now(), verification_evidence_json=json.dumps({"page_accessible": True, "apply_route_available": True, "closed_signal_found": False, "employer_identity_match": True}))
        session.add(job)
        session.flush()
        session.add(CampaignJob(campaign_id=campaign.id, job_posting_id=job.id))
        session.commit()
    response = client.post("/campaigns/campaign-job-package/jobs/job-package-test/prepare", cookies={"ai_session": token}, headers=headers)
    assert response.status_code == 202
    assert response.json()["campaign_id"] == "campaign-job-package"
    assert response.json()["application_status"] == "preparing"
    assert response.json()["package_ready"] is False
    combined_job = next(item for item in client.get("/jobs", cookies={"ai_session": token}).json() if item["id"] == "job-package-test")
    assert combined_job["campaign_id"] == "campaign-job-package"
    assert combined_job["application_status"] == "preparing"
    with workspace_context(RequestIdentity(user_id=authenticated_app["user_id"], workspace_id=authenticated_app["user_workspace_id"])), Session(authenticated_app["engine"]) as session:
        task = session.exec(select(AgentTask).where(AgentTask.task_type == "job_application_draft")).one()
        assert json.loads(task.input_json)["job_id"] == "job-package-test"
        assert task.agent_role == "resume_and_email_team"
        reminder = session.exec(
            select(ReviewException).where(ReviewException.category == "profile_refresh_suggested")
        ).one()
        assert reminder.status == "open"
        assert "nothing is blocked" in reminder.explanation


def test_revalidation_launches_dedicated_verifier_without_broad_search(authenticated_app, monkeypatch):
    from backend.app.agents import job_verification_runtime
    from backend.app.workflow.engine import WorkflowEngine

    identity = RequestIdentity(
        user_id=authenticated_app["user_id"],
        workspace_id=authenticated_app["user_workspace_id"],
    )
    captured: list[str | None] = []

    def fake_prepare(*, campaign, job, session, settings):
        captured.append(job.job_id)
        return "job-revalidation-test-run"

    monkeypatch.setattr(job_verification_runtime, "prepare_job_verification_run", fake_prepare)
    monkeypatch.setattr(job_verification_runtime.JobVerificationRuntime, "launch", lambda self, run_id: None)
    with workspace_context(identity), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.company_id == "company-shared")).one()
        campaign = Campaign(
            campaign_id="campaign-targeted-revalidation",
            name="Targeted revalidation",
            campaign_type="listed_job_search",
            status="active",
            sending_mode="prepare_only",
        )
        session.add(campaign)
        session.flush()
        job = JobPosting(
            job_id="job-targeted-revalidation",
            company_id=company.id,
            external_company_id=company.company_id,
            title="One listing only",
            source_url="https://example.com/jobs/target",
            canonical_url="https://example.com/jobs/target",
            application_url="https://example.com/jobs/target/apply",
            source_domain="example.com",
            source_kind="employer",
            fingerprint="job-targeted-revalidation",
        )
        session.add(job)
        session.flush()
        task = AgentTask(
            task_id="task-targeted-revalidation",
            campaign_id=campaign.id,
            company_id=company.id,
            agent_role="vacancy_verifier",
            task_type="job_verification",
            input_json=json.dumps({"job_id": job.job_id}),
        )
        session.add(task)
        session.commit()

        WorkflowEngine(session, authenticated_app["settings"]).process(task)

        assert captured == ["job-targeted-revalidation"]
        assert task.run_id == "job-revalidation-test-run"
        assert "checking only One listing only" in task.narrative


def test_user_can_manually_validate_a_job_with_audited_confirmation(authenticated_app):
    client = authenticated_app["client"]
    token = authenticated_app["user_token"]
    headers = {"X-CSRF-Token": csrf_token(token, authenticated_app["settings"])}
    identity = RequestIdentity(
        user_id=authenticated_app["user_id"],
        workspace_id=authenticated_app["user_workspace_id"],
    )
    with workspace_context(identity), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.company_id == "company-shared")).one()
        campaign = Campaign(
            campaign_id="campaign-manual-job-validation",
            name="Manual job validation",
            campaign_type="listed_job_search",
            status="active",
            sending_mode="prepare_only",
        )
        session.add(campaign)
        session.flush()
        job = JobPosting(
            job_id="job-manual-validation",
            company_id=company.id,
            external_company_id=company.company_id,
            title="Manually checked role",
            source_url="https://example.com/jobs/manual",
            canonical_url="https://example.com/jobs/manual",
            application_url="https://example.com/jobs/manual/apply",
            source_domain="example.com",
            source_kind="ats",
            fingerprint="job-manual-validation",
            vacancy_status="needs_review",
            review_flags_json=json.dumps(["missing_date_posted"]),
            verification_evidence_json=json.dumps(
                {"page_accessible": True, "apply_route_available": True, "closed_signal_found": False}
            ),
        )
        session.add(job)
        session.flush()
        session.add(CampaignJob(campaign_id=campaign.id, job_posting_id=job.id))
        session.commit()

    response = client.post(
        "/jobs/job-manual-validation/manual-validation",
        json={"confirmed_open": True, "note": "Checked the listing and application form."},
        cookies={"ai_session": token},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["vacancy_status"] == "verified_open"
    assert response.json()["last_verified_at"] is not None
    assert response.json()["verification_evidence"]["manual_confirmation"]["note"] == "Checked the listing and application form."
    with workspace_context(identity), Session(authenticated_app["engine"]) as session:
        audit = session.exec(
            select(AuditLog).where(AuditLog.action == "job_listing_manually_validated")
        ).one()
        assert audit.entity_id == "job-manual-validation"
        assert audit.result_status == "verified_open"


def test_revalidate_reassesses_recent_evidence_before_launching_an_agent(authenticated_app):
    client = authenticated_app["client"]
    token = authenticated_app["user_token"]
    headers = {"X-CSRF-Token": csrf_token(token, authenticated_app["settings"])}
    identity = RequestIdentity(
        user_id=authenticated_app["user_id"],
        workspace_id=authenticated_app["user_workspace_id"],
    )
    with workspace_context(identity), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.company_id == "company-shared")).one()
        campaign = Campaign(
            campaign_id="campaign-reassess-job-evidence",
            name="Reassess job evidence",
            campaign_type="listed_job_search",
            status="active",
            sending_mode="prepare_only",
        )
        session.add(campaign)
        session.flush()
        job = JobPosting(
            job_id="job-reassess-evidence",
            company_id=company.id,
            external_company_id=company.company_id,
            title="Role with a future deadline",
            source_url="https://example.com/jobs/reassess",
            canonical_url="https://example.com/jobs/reassess",
            application_url="https://example.com/jobs/reassess/apply",
            source_domain="example.com",
            source_kind="ats",
            fingerprint="job-reassess-evidence",
            vacancy_status="needs_review",
            valid_through=utc_now() + timedelta(days=14),
            last_verified_at=utc_now(),
            review_flags_json=json.dumps(["missing_date_posted", "untrusted_verification_source"]),
            verification_evidence_json=json.dumps(
                {
                    "page_accessible": True,
                    "apply_route_available": True,
                    "closed_signal_found": False,
                    "employer_identity_match": True,
                    "http_status": 200,
                }
            ),
        )
        session.add(job)
        session.flush()
        session.add(CampaignJob(campaign_id=campaign.id, job_posting_id=job.id))
        session.commit()

    response = client.post(
        "/jobs/job-reassess-evidence/revalidate",
        cookies={"ai_session": token},
        headers=headers,
    )

    assert response.status_code == 202
    assert response.json() == {
        "job_id": "job-reassess-evidence",
        "status": "verified_open",
        "reassessed_existing_evidence": True,
    }
    with workspace_context(identity), Session(authenticated_app["engine"]) as session:
        job = session.exec(select(JobPosting).where(JobPosting.job_id == "job-reassess-evidence")).one()
        assert job.vacancy_status == "verified_open"
        assert json.loads(job.review_flags_json) == ["missing_date_posted"]
        tasks = session.exec(
            select(AgentTask).where(AgentTask.input_json.contains("job-reassess-evidence"))
        ).all()
        assert tasks == []


def test_job_discovered_company_reuses_fit_and_can_queue_outreach_documents(authenticated_app):
    client = authenticated_app["client"]
    token = authenticated_app["user_token"]
    headers = {"X-CSRF-Token": csrf_token(token, authenticated_app["settings"])}
    identity = RequestIdentity(
        user_id=authenticated_app["user_id"],
        workspace_id=authenticated_app["user_workspace_id"],
    )
    with workspace_context(identity), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.company_id == "company-shared")).one()
        campaign = Campaign(
            campaign_id="campaign-job-company-documents",
            name="Job-discovered companies",
            campaign_type="listed_job_search",
            status="active",
            sending_mode="prepare_only",
        )
        session.add(campaign)
        session.flush()
        job = JobPosting(
            job_id="job-company-fit",
            company_id=company.id,
            external_company_id=company.company_id,
            title="Public Administration Specialist",
            source_url="https://example.com/jobs/company-fit",
            canonical_url="https://example.com/jobs/company-fit",
            application_url="https://example.com/jobs/company-fit/apply",
            source_domain="example.com",
            source_kind="employer",
            fingerprint="job-company-fit",
        )
        session.add(job)
        session.flush()
        session.add_all(
            [
                CampaignJob(campaign_id=campaign.id, job_posting_id=job.id),
                JobFitEvaluation(
                    evaluation_id="job-company-fit-evaluation",
                    job_posting_id=job.id,
                    external_job_id=job.job_id,
                    company_fit_score=0.94,
                    role_fit_score=0.81,
                    decision="promising",
                    reasons_json=json.dumps([{"text": "Strong public-sector alignment."}]),
                    confidence=0.9,
                ),
            ]
        )
        session.commit()
        company_pk = company.id
        campaign_pk = campaign.id

    companies = client.get("/companies", cookies={"ai_session": token}).json()
    company_response = next(item for item in companies if item["company_id"] == "company-shared")
    assert company_response["fit_score"] == 0.94
    assert company_response["fit_decision"] == "promising"
    assert company_response["fit_reasons"] == [{"text": "Strong public-sector alignment."}]

    response = client.post(
        "/companies/company-shared/prepare",
        cookies={"ai_session": token},
        headers=headers,
    )
    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    with workspace_context(identity), Session(authenticated_app["engine"]) as session:
        task = session.exec(
            select(AgentTask).where(
                AgentTask.company_id == company_pk,
                AgentTask.task_type == "contact_research",
            )
        ).one()
        assert task.campaign_id == campaign_pk
        assert task.agent_role == "contact_researcher"

    refreshed = client.get("/companies", cookies={"ai_session": token}).json()
    refreshed_company = next(item for item in refreshed if item["company_id"] == "company-shared")
    assert refreshed_company["application_preparation_status"] == "queued"
    assert refreshed_company["can_draft_application"] is False
    assert refreshed_company["application_draft_block_reason"] == "application_preparation_in_progress"


def test_listed_job_application_language_prefers_listing_language_and_supports_legacy_records():
    from backend.app.jobs.application_packages import _listed_job_application_language

    explicit = JobPosting(
        job_id="explicit-language", external_company_id="company", title="Engineer",
        source_url="https://example.com/1", canonical_url="https://example.com/1",
        application_url="https://example.com/1/apply", source_domain="example.com",
        source_kind="employer", fingerprint="explicit-language",
        languages_json=json.dumps(["English", "German"]), raw_json=json.dumps({"listing_language": "German"}),
    )
    legacy = JobPosting(
        job_id="legacy-language", external_company_id="company", title="Engineer",
        source_url="https://example.com/2", canonical_url="https://example.com/2",
        application_url="https://example.com/2/apply", source_domain="example.com",
        source_kind="employer", fingerprint="legacy-language",
        languages_json=json.dumps(["German", "English"]),
    )

    assert _listed_job_application_language(explicit) == "German"
    assert _listed_job_application_language(legacy) == "German"


def test_workflow_worker_reconciles_running_job_research(authenticated_app, monkeypatch):
    from backend.app.workflow.engine import WorkflowEngine, WorkflowWorker

    with workspace_context(RequestIdentity(user_id=authenticated_app["user_id"], workspace_id=authenticated_app["user_workspace_id"])), Session(authenticated_app["engine"]) as session:
        campaign = Campaign(campaign_id="campaign-job-reconcile", name="Reconcile jobs", campaign_type="listed_job_search", status="researching")
        session.add(campaign)
        session.flush()
        task = AgentTask(task_id="task-job-reconcile", campaign_id=campaign.id, agent_role="vacancy_scout", task_type="job_research", status="running", run_id="run-job-reconcile")
        session.add(task)
        session.commit()

    reconciled: list[str] = []

    def fake_reconcile(self, task):
        reconciled.append(task.task_type)
        task.status = "completed"
        self.session.add(task)
        self.session.commit()

    monkeypatch.setattr(WorkflowEngine, "reconcile", fake_reconcile)
    assert WorkflowWorker(settings=authenticated_app["settings"]).run_once() is True
    assert reconciled == ["job_research"]


def test_company_application_reconcile_indexes_documents_without_job_context(authenticated_app, monkeypatch):
    from backend.app.workflow.engine import WorkflowEngine

    identity = RequestIdentity(
        user_id=authenticated_app["user_id"],
        workspace_id=authenticated_app["user_workspace_id"],
    )
    with workspace_context(identity), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.company_id == "company-shared")).one()
        campaign = Campaign(
            campaign_id="campaign-company-reconcile",
            name="Company document preparation",
            campaign_type="initiative_outreach",
            status="preparing",
            sending_mode="prepare_only",
        )
        session.add(campaign)
        session.flush()
        task = AgentTask(
            task_id="task-company-draft-reconcile",
            campaign_id=campaign.id,
            company_id=company.id,
            agent_role="resume_and_email_team",
            task_type="application_draft",
            status="running",
            run_id="application-draft-company-reconcile",
        )
        draft = EmailDraft(
            draft_id="draft-company-reconcile",
            company_id=company.id,
            external_company_id=company.company_id,
            external_contact_id="contact-company-reconcile",
            subject="Tailored outreach",
            body_text="Hello",
            confidence=0.9,
            raw_json="{}",
        )
        session.add_all([task, draft])
        session.commit()

        indexed: list[dict[str, object]] = []
        engine = WorkflowEngine(session, authenticated_app["settings"])
        monkeypatch.setattr(engine, "_index_documents", lambda _task, _company, **kwargs: indexed.append(kwargs))
        engine._reconcile_draft(task, {"status": "imported"})

        assert indexed == [{}]
        assert task.status == "completed"
        assert task.progress == 100


def test_workflow_worker_reconciles_running_job_application_draft(authenticated_app, monkeypatch):
    from backend.app.workflow.engine import WorkflowEngine, WorkflowWorker

    with workspace_context(RequestIdentity(user_id=authenticated_app["user_id"], workspace_id=authenticated_app["user_workspace_id"])), Session(authenticated_app["engine"]) as session:
        campaign = Campaign(campaign_id="campaign-job-draft-reconcile", name="Tailor job", campaign_type="listed_job_search", status="active")
        session.add(campaign)
        session.flush()
        task = AgentTask(task_id="task-job-draft-reconcile", campaign_id=campaign.id, agent_role="resume_and_email_team", task_type="job_application_draft", status="running", run_id="run-job-draft-reconcile")
        session.add(task)
        session.commit()

    reconciled: list[str] = []

    def fake_reconcile(self, task):
        reconciled.append(task.task_type)
        task.status = "completed"
        self.session.add(task)
        self.session.commit()

    monkeypatch.setattr(WorkflowEngine, "reconcile", fake_reconcile)
    assert WorkflowWorker(settings=authenticated_app["settings"]).run_once() is True
    assert reconciled == ["job_application_draft"]


def test_unresolved_worker_failure_becomes_exception(authenticated_app):
    from backend.app.auth.context import RequestIdentity, workspace_context
    from backend.app.workflow.engine import WorkflowEngine

    with workspace_context(
        RequestIdentity(
            user_id=authenticated_app["user_id"],
            workspace_id=authenticated_app["user_workspace_id"],
        )
    ), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.name == "User Company")).one()
        task = AgentTask(
            task_id="task-unsupported",
            company_id=company.id,
            agent_role="test_specialist",
            task_type="unsupported",
            max_attempts=1,
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        WorkflowEngine(session, authenticated_app["settings"]).process(task)
        session.refresh(task)
        exception = session.exec(select(ReviewException).where(ReviewException.agent_task_id == task.id)).one()
        assert task.status == "blocked"
        assert exception.status == "open"

    response = authenticated_app["client"].get(
        "/exceptions",
        cookies={"ai_session": authenticated_app["user_token"]},
    )
    assert response.status_code == 200
    assert response.json()[0]["company_name"] == "User Company"
    assert response.json()[0]["external_company_id"] == "company-shared"


def test_contact_research_without_imported_contact_blocks_before_drafting(authenticated_app):
    from backend.app.auth.context import RequestIdentity, workspace_context
    from backend.app.workflow.engine import WorkflowEngine

    with workspace_context(
        RequestIdentity(authenticated_app["user_id"], authenticated_app["user_workspace_id"])
    ), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.name == "User Company")).one()
        campaign = Campaign(campaign_id="campaign-contact-missing", name="Contact test")
        session.add(campaign)
        session.commit()
        session.refresh(campaign)
        session.add(CampaignCompany(campaign_id=campaign.id, company_id=company.id, stage="qualified"))
        task = AgentTask(
            task_id="task-contact-missing",
            campaign_id=campaign.id,
            company_id=company.id,
            agent_role="contact_researcher",
            task_type="contact_research",
            status="running",
            run_id="contact-missing",
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        WorkflowEngine(session, authenticated_app["settings"])._reconcile_contact_research(
            task, {"status": "imported"}
        )

        session.refresh(task)
        exception = session.exec(select(ReviewException).where(ReviewException.agent_task_id == task.id)).one()
        drafts = session.exec(
            select(AgentTask).where(
                AgentTask.campaign_id == campaign.id,
                AgentTask.company_id == company.id,
                AgentTask.task_type == "application_draft",
            )
        ).all()
        assert task.status == "blocked"
        assert exception.category == "contact_not_found"
        assert company.name in exception.title
        assert "drafting has not been started" in exception.explanation
        assert drafts == []


def test_company_research_queues_contact_research_before_drafting(authenticated_app):
    from backend.app.auth.context import RequestIdentity, workspace_context
    from backend.app.workflow.engine import WorkflowEngine

    with workspace_context(
        RequestIdentity(authenticated_app["user_id"], authenticated_app["user_workspace_id"])
    ), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.name == "User Company")).one()
        imported = ImportedFile(
            run_id="company-research-import",
            path="companies/company-shared.json",
            filename="company-shared.json",
            schema_name="company_candidate.schema.json",
            status="imported",
        )
        campaign = Campaign(campaign_id="campaign-contact-first", name="Contact first")
        session.add(imported)
        session.add(campaign)
        session.commit()
        session.refresh(imported)
        session.refresh(campaign)
        company.imported_file_id = imported.id
        task = AgentTask(
            task_id="task-company-research-contact-first",
            campaign_id=campaign.id,
            agent_role="company_researcher",
            task_type="company_research",
            status="running",
            run_id=imported.run_id,
        )
        session.add(company)
        session.add(task)
        session.commit()
        session.refresh(task)

        WorkflowEngine(session, authenticated_app["settings"])._reconcile_research(
            task, {"status": "imported", "artifact_counts": {"companies": 1}}
        )

        next_tasks = session.exec(
            select(AgentTask).where(AgentTask.campaign_id == campaign.id, AgentTask.company_id == company.id)
        ).all()
        assert [item.task_type for item in next_tasks] == ["contact_research"]


def test_contact_research_imported_contact_queues_drafting(authenticated_app):
    from backend.app.auth.context import RequestIdentity, workspace_context
    from backend.app.workflow.engine import WorkflowEngine

    with workspace_context(
        RequestIdentity(authenticated_app["user_id"], authenticated_app["user_workspace_id"])
    ), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.name == "User Company")).one()
        campaign = Campaign(campaign_id="campaign-contact-found", name="Contact test")
        session.add(campaign)
        session.commit()
        session.refresh(campaign)
        session.add(
            Contact(
                contact_id="contact-researched",
                company_id=company.id,
                external_company_id=company.company_id,
                raw_email="careers@shared.example",
                normalized_recipient_email="careers@shared.example",
                email_source="company_site",
                confidence=0.9,
                source_refs_json='["https://shared.example/careers"]',
                review_flags_json="[]",
                raw_json="{}",
            )
        )
        task = AgentTask(
            task_id="task-contact-found",
            campaign_id=campaign.id,
            company_id=company.id,
            agent_role="contact_researcher",
            task_type="contact_research",
            status="running",
            run_id="contact-found",
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        WorkflowEngine(session, authenticated_app["settings"])._reconcile_contact_research(
            task, {"status": "imported"}
        )

        session.refresh(task)
        draft_task = session.exec(
            select(AgentTask).where(
                AgentTask.campaign_id == campaign.id,
                AgentTask.company_id == company.id,
                AgentTask.task_type == "application_draft",
            )
        ).one()
        assert task.status == "completed"
        assert draft_task.status == "queued"


def test_contact_research_launch_prepares_exact_company_run(authenticated_app, monkeypatch):
    from backend.app.agents.company_research_runtime import CompanyResearchRuntime, ResearchLaunchResult
    from backend.app.auth.context import RequestIdentity, workspace_context
    from backend.app.workflow.engine import WorkflowEngine

    launched: list[str] = []

    def fake_launch(self, run_id: str) -> ResearchLaunchResult:
        launched.append(run_id)
        return ResearchLaunchResult(run_id=run_id, status="running", command=[], workdir=self._run_root(run_id))

    monkeypatch.setattr(CompanyResearchRuntime, "launch", fake_launch)
    with workspace_context(
        RequestIdentity(authenticated_app["user_id"], authenticated_app["user_workspace_id"])
    ), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.name == "User Company")).one()
        campaign = Campaign(campaign_id="campaign-contact-launch", name="Contact launch")
        session.add(campaign)
        session.commit()
        session.refresh(campaign)
        task = AgentTask(
            task_id="task-contact-launch",
            campaign_id=campaign.id,
            company_id=company.id,
            agent_role="contact_researcher",
            task_type="contact_research",
        )
        session.add(task)
        session.commit()
        session.refresh(task)

        WorkflowEngine(session, authenticated_app["settings"]).process(task)

        session.refresh(task)
        assert task.status == "running"
        assert task.run_id == launched[0]
        brief = json.loads((scoped_runs_root(authenticated_app["settings"].runs_root) / task.run_id / "input" / "campaign.json").read_text(encoding="utf-8"))
        assert brief["max_companies"] == 1
        assert "User Company" in brief["notes"]
        assert "Do not discover other companies" in brief["notes"]


def test_retry_upgrades_existing_missing_contact_draft_to_contact_research(authenticated_app):
    with workspace_context(
        RequestIdentity(authenticated_app["user_id"], authenticated_app["user_workspace_id"])
    ), Session(authenticated_app["engine"]) as session:
        company = session.exec(select(Company).where(Company.name == "User Company")).one()
        task = AgentTask(
            task_id="task-legacy-missing-contact",
            company_id=company.id,
            agent_role="resume_and_email_team",
            task_type="application_draft",
            status="blocked",
            attempt_count=3,
            last_error="409: Application drafts require an imported contact.",
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        exception = ReviewException(
            exception_id="exception-legacy-missing-contact",
            company_id=company.id,
            agent_task_id=task.id,
            category="agent_failure",
            title="A specialist needs help continuing",
            explanation=task.last_error or "",
            recommended_action="Retry.",
        )
        session.add(exception)
        session.commit()

    token = authenticated_app["user_token"]
    response = authenticated_app["client"].post(
        "/exceptions/exception-legacy-missing-contact/resolve",
        cookies={"ai_session": token},
        headers={"X-CSRF-Token": csrf_token(token, authenticated_app["settings"])},
        json={"action": "retry"},
    )
    assert response.status_code == 200
    with workspace_context(
        RequestIdentity(authenticated_app["user_id"], authenticated_app["user_workspace_id"])
    ), Session(authenticated_app["engine"]) as session:
        task = session.exec(select(AgentTask).where(AgentTask.task_id == "task-legacy-missing-contact")).one()
        assert task.task_type == "contact_research"
        assert task.agent_role == "contact_researcher"
        assert task.status == "queued"
        assert task.attempt_count == 0
        assert task.run_id is None
