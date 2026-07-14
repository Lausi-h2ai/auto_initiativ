from __future__ import annotations

import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, EmailStr, Field
from sqlmodel import Session, select

from backend.app.auth.service import AuthService, CredentialVault, GoogleOAuthClient, require_role
from backend.app.core.config import Settings, get_settings
from backend.app.db.models import AdminAccessAudit, GmailConnection, Invitation, User, Workspace, utc_now
from backend.app.db.session import get_session


router = APIRouter(tags=["authentication"])
GMAIL_SCOPES = ("openid", "email", "profile", "https://www.googleapis.com/auth/gmail.send")


class InvitationCreate(BaseModel):
    email: EmailStr
    role: str = "user"


class LocalRegistrationCreate(BaseModel):
    display_name: str = Field(min_length=2, max_length=100)
    email: EmailStr


class LocalAccountSwitch(BaseModel):
    user_id: int


def _require_local_auth(settings: Settings) -> None:
    if settings.auth_required:
        raise HTTPException(status_code=403, detail="Local account access is disabled when authentication is required.")


def _set_session_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        "ai_session",
        raw_token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        max_age=settings.auth_session_days * 86400,
        path="/",
    )


def _request_user(request: Request, session: Session) -> User:
    user_id = getattr(request.state, "user_id", None)
    user = session.get(User, user_id) if user_id is not None else None
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


@router.get("/auth/google/start")
def google_start(
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    _state, url = AuthService(session, settings).start_oauth()
    return RedirectResponse(url, status_code=303)


@router.get("/auth/google/callback")
def google_callback(
    code: str,
    state: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    service = AuthService(session, settings)
    oauth_state = service.consume_state(state)
    identity = GoogleOAuthClient(settings).exchange_identity(
        code=code,
        verifier=oauth_state.code_verifier,
        redirect_uri=oauth_state.redirect_uri,
    )
    user = service.authenticate_google_identity(identity)
    raw_token = service.create_session(user)
    response = RedirectResponse("/dashboard", status_code=303)
    response.set_cookie(
        "ai_session",
        raw_token,
        httponly=True,
        secure=settings.secure_cookies,
        samesite="lax",
        max_age=settings.auth_session_days * 86400,
        path="/",
    )
    return response


@router.post("/auth/logout")
def logout(
    request: Request,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, bool]:
    AuthService(session, settings).revoke_session(request.cookies.get("ai_session"))
    response.delete_cookie("ai_session", path="/")
    return {"logged_out": True}


@router.get("/auth/local/capabilities")
def local_auth_capabilities(settings: Settings = Depends(get_settings)) -> dict[str, bool]:
    return {"registration_enabled": not settings.auth_required}


@router.get("/auth/local/accounts")
def local_accounts(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[dict[str, object]]:
    _require_local_auth(settings)
    users = session.exec(select(User).where(User.status == "active").order_by(User.display_name, User.id)).all()
    workspaces = {item.owner_user_id: item for item in session.exec(select(Workspace).where(Workspace.status == "active")).all()}
    switchable = [user for user in users if user.google_subject == "bootstrap:legacy" or user.google_subject.startswith(("dev:", "local:"))]
    return [
        {
            "id": user.id,
            "display_name": user.display_name,
            "email": user.email,
            "workspace": {"id": workspaces[user.id].workspace_id, "name": workspaces[user.id].name},
            "is_current": user.id == getattr(request.state, "user_id", None),
        }
        for user in switchable
        if user.id in workspaces
    ]


@router.post("/auth/local/switch")
def local_switch(
    payload: LocalAccountSwitch,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    _require_local_auth(settings)
    user = session.get(User, payload.user_id)
    if user is None or user.status != "active" or not (
        user.google_subject == "bootstrap:legacy" or user.google_subject.startswith(("dev:", "local:"))
    ):
        raise HTTPException(status_code=404, detail="Local account not found.")
    workspace = session.exec(select(Workspace).where(Workspace.owner_user_id == user.id, Workspace.status == "active")).first()
    if workspace is None:
        raise HTTPException(status_code=409, detail="This account has no active workspace.")
    raw_token = AuthService(session, settings).create_session(user)
    _set_session_cookie(response, raw_token, settings)
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "workspace": {"id": workspace.workspace_id, "name": workspace.name},
    }


@router.post("/auth/local/register", status_code=201)
def local_register(
    payload: LocalRegistrationCreate,
    response: Response,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    _require_local_auth(settings)
    email = str(payload.email).strip().lower()
    display_name = payload.display_name.strip()
    if len(display_name) < 2:
        raise HTTPException(status_code=422, detail="Display name must contain at least two visible characters.")

    user = session.exec(select(User).where(User.email == email)).first()
    if user is not None and user.google_subject != "bootstrap:legacy" and not user.google_subject.startswith(("dev:", "local:")):
        raise HTTPException(status_code=409, detail="This email belongs to an externally authenticated account.")
    if user is None:
        user = User(
            google_subject=f"local:{uuid4()}",
            email=email,
            display_name=display_name,
            role="admin",
        )
        session.add(user)
        session.flush()
        session.add(
            Workspace(
                workspace_id=f"workspace-local-{uuid4()}",
                owner_user_id=user.id,
                name=f"{display_name}'s workspace",
            )
        )
        session.commit()
        session.refresh(user)
    else:
        if user.status != "active":
            raise HTTPException(status_code=403, detail="This local account is not active.")
        user.display_name = display_name
        user.updated_at = utc_now()
        user.last_login_at = utc_now()
        session.add(user)
        session.commit()

    workspace = session.exec(select(Workspace).where(Workspace.owner_user_id == user.id)).first()
    if workspace is None:
        workspace = Workspace(
            workspace_id=f"workspace-local-{uuid4()}",
            owner_user_id=user.id,
            name=f"{display_name}'s workspace",
        )
        session.add(workspace)
        session.commit()
        session.refresh(workspace)
    raw_token = AuthService(session, settings).create_session(user)
    _set_session_cookie(response, raw_token, settings)
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "workspace": {"id": workspace.workspace_id, "name": workspace.name},
    }


@router.post("/auth/google/gmail/start")
def gmail_start(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, str]:
    user = _request_user(request, session)
    _state, url = AuthService(session, settings).start_oauth(
        purpose="gmail",
        user_id=user.id,
        callback_path="/auth/google/gmail/callback",
        scopes=GMAIL_SCOPES,
    )
    return {"authorization_url": url}


@router.get("/auth/google/gmail/callback")
def gmail_callback(
    code: str,
    state: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> RedirectResponse:
    service = AuthService(session, settings)
    oauth_state = service.consume_state(state, purpose="gmail")
    if oauth_state.user_id is None:
        raise HTTPException(status_code=401, detail="The Gmail connection request is not associated with a user.")
    identity, credentials_json = GoogleOAuthClient(settings).exchange_credentials(
        code=code,
        verifier=oauth_state.code_verifier,
        redirect_uri=oauth_state.redirect_uri,
        scopes=GMAIL_SCOPES,
    )
    user = session.get(User, oauth_state.user_id)
    if user is None or user.status != "active" or identity.subject != user.google_subject:
        raise HTTPException(status_code=403, detail="Connect the same Google identity used to sign in.")
    credential_payload = json.loads(credentials_json)
    connection = session.exec(select(GmailConnection).where(GmailConnection.user_id == user.id)).first()
    if connection is None:
        connection = GmailConnection(
            connection_id=f"gmail-{uuid4()}",
            user_id=user.id,
            google_subject=identity.subject,
            email=identity.email,
            encrypted_credentials="",
        )
    connection.google_subject = identity.subject
    connection.email = identity.email
    connection.encrypted_credentials = CredentialVault(settings).encrypt(credentials_json)
    connection.scopes_json = json.dumps(credential_payload.get("scopes", list(GMAIL_SCOPES)))
    connection.status = "connected"
    connection.updated_at = utc_now()
    connection.revoked_at = None
    session.add(connection)
    session.commit()
    return RedirectResponse("/dashboard#settings", status_code=303)


@router.get("/gmail/connection")
def gmail_status(request: Request, session: Session = Depends(get_session)) -> dict[str, object]:
    user = _request_user(request, session)
    connection = session.exec(select(GmailConnection).where(GmailConnection.user_id == user.id)).first()
    return {
        "connected": bool(connection and connection.status == "connected"),
        "email": connection.email if connection and connection.status == "connected" else None,
        "scopes": json.loads(connection.scopes_json) if connection and connection.scopes_json else [],
        "connected_at": connection.connected_at if connection and connection.status == "connected" else None,
    }


@router.delete("/gmail/connection")
def gmail_disconnect(request: Request, session: Session = Depends(get_session)) -> dict[str, bool]:
    user = _request_user(request, session)
    connection = session.exec(select(GmailConnection).where(GmailConnection.user_id == user.id)).first()
    if connection is not None:
        connection.status = "disconnected"
        connection.encrypted_credentials = ""
        connection.revoked_at = utc_now()
        connection.updated_at = utc_now()
        session.add(connection)
        session.commit()
    return {"connected": False}


@router.get("/me")
def me(
    request: Request,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> dict[str, object]:
    user = _request_user(request, session)
    workspace = session.exec(select(Workspace).where(Workspace.owner_user_id == user.id)).one()
    return {
        "id": user.id,
        "email": user.email,
        "display_name": user.display_name,
        "avatar_url": user.avatar_url,
        "role": user.role,
        "workspace": {"id": workspace.workspace_id, "name": workspace.name},
        "csrf_token": request.state.csrf_token,
        "local_registration_enabled": not settings.auth_required,
    }


@router.get("/admin/workspaces")
def admin_workspaces(request: Request, session: Session = Depends(get_session)) -> list[dict[str, object]]:
    user = _request_user(request, session)
    require_role(user, "admin")
    workspaces = session.exec(select(Workspace).order_by(Workspace.created_at.desc())).all()
    owners = {owner.id: owner for owner in session.exec(select(User)).all()}
    return [
        {
            "id": item.workspace_id,
            "name": item.name,
            "status": item.status,
            "owner_email": owners[item.owner_user_id].email if item.owner_user_id in owners else None,
        }
        for item in workspaces
    ]


@router.post("/admin/invitations", status_code=201)
def create_invitation(
    payload: InvitationCreate,
    request: Request,
    session: Session = Depends(get_session),
) -> dict[str, object]:
    user = _request_user(request, session)
    require_role(user, "admin")
    email = str(payload.email).strip().lower()
    role = payload.role.strip().lower()
    if role not in {"user", "admin"}:
        raise HTTPException(status_code=422, detail="Role must be user or admin.")
    existing_user = session.exec(select(User).where(User.email == email)).first()
    if existing_user is not None:
        raise HTTPException(status_code=409, detail="An account already exists for this email.")
    invitation = session.exec(select(Invitation).where(Invitation.email == email)).first()
    if invitation is None:
        invitation = Invitation(
            invitation_id=f"invitation-{uuid4()}",
            email=email,
            role=role,
            invited_by_user_id=user.id,
        )
    else:
        invitation.role = role
        invitation.status = "pending"
        invitation.invited_by_user_id = user.id
    session.add(invitation)
    session.add(
        AdminAccessAudit(
            access_id=f"access-{uuid4()}",
            admin_user_id=user.id,
            target_workspace_id=request.state.workspace_id,
            action="invite_user",
            resource_type="invitation",
            resource_id=email,
        )
    )
    session.commit()
    return {"id": invitation.invitation_id, "email": invitation.email, "role": invitation.role, "status": invitation.status}
