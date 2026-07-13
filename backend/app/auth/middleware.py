from __future__ import annotations

import hmac
from datetime import timezone
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlmodel import Session, select
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from backend.app.auth.context import RequestIdentity, reset_identity, set_identity
from backend.app.auth.service import csrf_token, token_hash
from backend.app.core.config import get_settings
from backend.app.db import session as db_session_module
from backend.app.db.models import AdminAccessAudit, AuthSession, User, Workspace, utc_now


PUBLIC_PREFIXES = ("/auth/google/", "/auth/local/", "/static/", "/assets/")
PUBLIC_PATHS = {"/health", "/login", "/register", "/favicon.ico", "/monitoring/client-errors"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _is_expired(value: object) -> bool:
    if not hasattr(value, "tzinfo"):
        return True
    timestamp = value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp <= utc_now()


class AuthWorkspaceMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        settings = get_settings()
        if not settings.auth_required:
            with Session(db_session_module.engine) as session:
                raw_token = request.cookies.get("ai_session")
                auth_session = (
                    session.exec(select(AuthSession).where(AuthSession.token_hash == token_hash(raw_token))).first()
                    if raw_token
                    else None
                )
                user = None
                if auth_session is not None and auth_session.revoked_at is None and not _is_expired(auth_session.expires_at):
                    user = session.get(User, auth_session.user_id)
                    if user is None or user.status != "active":
                        user = None
                    else:
                        auth_session.last_seen_at = utc_now()
                        session.add(auth_session)
                        session.commit()
                if user is None and settings.dev_auth_bypass_email:
                    email = settings.dev_auth_bypass_email.strip().lower()
                    user = session.exec(select(User).where(User.email == email)).first()
                    if user is None:
                        user = User(
                            google_subject=f"dev:{email}",
                            email=email,
                            display_name=email.split("@", 1)[0].replace(".", " ").title(),
                            role="admin",
                        )
                        session.add(user)
                        session.flush()
                        session.add(
                            Workspace(
                                workspace_id=f"workspace-dev-{uuid4()}",
                                owner_user_id=user.id,
                                name="Development workspace",
                            )
                        )
                        session.commit()
                if user is None:
                    return await call_next(request)
                workspace = session.exec(select(Workspace).where(Workspace.owner_user_id == user.id)).one()
                request.state.user_id = user.id
                request.state.workspace_id = workspace.id
                request.state.workspace_public_id = workspace.workspace_id
                request.state.role = user.role
                request.state.csrf_token = "development-bypass"
                identity = RequestIdentity(user_id=user.id, workspace_id=workspace.id, role=user.role)
            context_token = set_identity(identity)
            try:
                return await call_next(request)
            finally:
                reset_identity(context_token)
        path = request.url.path
        if path in PUBLIC_PATHS or any(path.startswith(prefix) for prefix in PUBLIC_PREFIXES):
            return await call_next(request)

        raw_token = request.cookies.get("ai_session")
        with Session(db_session_module.engine) as session:
            auth_session = (
                session.exec(select(AuthSession).where(AuthSession.token_hash == token_hash(raw_token))).first()
                if raw_token
                else None
            )
            if (
                auth_session is None
                or auth_session.revoked_at is not None
                or _is_expired(auth_session.expires_at)
            ):
                return self._unauthenticated(path)
            user = session.get(User, auth_session.user_id)
            workspace = (
                session.exec(select(Workspace).where(Workspace.owner_user_id == user.id)).first()
                if user is not None
                else None
            )
            if user is None or user.status != "active" or workspace is None or workspace.status != "active":
                return self._unauthenticated(path)

            target_workspace_id: int | None = None
            target_header = request.headers.get("X-Workspace-Id")
            if target_header and user.role == "admin":
                target = session.exec(select(Workspace).where(Workspace.workspace_id == target_header)).first()
                if target is None:
                    return JSONResponse({"detail": "Workspace not found."}, status_code=404)
                target_workspace_id = target.id
                if target.id != workspace.id:
                    if request.method not in SAFE_METHODS:
                        return JSONResponse({"detail": "Administrator workspace inspection is read-only."}, status_code=403)
                    session.add(
                        AdminAccessAudit(
                            access_id=f"access-{uuid4()}",
                            admin_user_id=user.id,
                            target_workspace_id=target.id,
                            action="inspect_workspace",
                            resource_type="http_request",
                            resource_id=path,
                        )
                    )
                    session.commit()

            if request.method not in SAFE_METHODS:
                supplied_csrf = request.headers.get("X-CSRF-Token", "")
                if not hmac.compare_digest(supplied_csrf, csrf_token(raw_token, settings)):
                    return JSONResponse({"detail": "CSRF validation failed."}, status_code=403)

            auth_session.last_seen_at = utc_now()
            session.add(auth_session)
            session.commit()
            request.state.user_id = user.id
            request.state.workspace_id = workspace.id
            request.state.workspace_public_id = workspace.workspace_id
            request.state.role = user.role
            request.state.csrf_token = csrf_token(raw_token, settings)
            identity = RequestIdentity(
                user_id=user.id,
                workspace_id=workspace.id,
                role=user.role,
                admin_target_workspace_id=target_workspace_id,
            )

        context_token = set_identity(identity)
        try:
            return await call_next(request)
        finally:
            reset_identity(context_token)

    @staticmethod
    def _unauthenticated(path: str) -> Response:
        if path in {"/", "/dashboard"}:
            return RedirectResponse("/login", status_code=303)
        return JSONResponse({"detail": "Authentication required."}, status_code=401)
