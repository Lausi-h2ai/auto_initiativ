from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from backend.app.auth.context import RequestIdentity, scoped_runs_root, workspace_context
from backend.app.auth.service import AuthService, GoogleIdentity, csrf_token
from backend.app.core.config import get_settings
from backend.app.db.models import (
    AdminAccessAudit,
    AgentTask,
    Campaign,
    CampaignCompany,
    Company,
    Contact,
    EmailDraft,
    ImportedFile,
    Invitation,
    MasterCvProfileSnapshot,
    PolicySnapshot,
    ReviewException,
    User,
    UserProfileSnapshot,
    Workspace,
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


def test_local_registration_creates_and_switches_fresh_workspaces(client):
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

    switched_back = client.post(
        "/auth/local/register",
        json={"display_name": "Fresh One", "email": "fresh-one@example.com"},
    )
    assert switched_back.status_code == 201
    assert client.get("/me").json()["id"] == first_me.json()["id"]


def test_local_registration_is_disabled_in_authenticated_mode(authenticated_app):
    response = authenticated_app["client"].post(
        "/auth/local/register",
        json={"display_name": "Not Allowed", "email": "blocked@example.com"},
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Local registration is disabled when authentication is required."


def test_workspace_queries_and_duplicate_ids_are_isolated(authenticated_app):
    client = authenticated_app["client"]
    admin = client.get("/companies", cookies={"ai_session": authenticated_app["admin_token"]})
    user = client.get("/companies", cookies={"ai_session": authenticated_app["user_token"]})

    assert admin.status_code == 200
    assert user.status_code == 200
    assert [item["name"] for item in admin.json()] == ["Admin Company"]
    assert [item["name"] for item in user.json()] == ["User Company"]


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


def test_campaign_creation_is_on_rails_and_enqueues_research(authenticated_app):
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
    assert response.json()["status"] == "active"
    assert response.json()["active_task_count"] == 1

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
