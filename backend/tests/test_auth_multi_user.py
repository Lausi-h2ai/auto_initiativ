from __future__ import annotations

import json
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, select

from backend.app.auth.context import RequestIdentity, workspace_context
from backend.app.auth.service import AuthService, GoogleIdentity, csrf_token
from backend.app.core.config import get_settings
from backend.app.db.models import AdminAccessAudit, Company, Invitation, User, Workspace


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
                session.commit()

        admin_workspace_id = admin_workspace.id
        admin_workspace_public_id = admin_workspace.workspace_id
        user_workspace_id = user_workspace.id
        user_workspace_public_id = user_workspace.workspace_id

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
        }


def test_unauthenticated_api_is_rejected(authenticated_app):
    response = authenticated_app["client"].get("/companies", follow_redirects=False)
    assert response.status_code == 401


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
