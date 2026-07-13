from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import timedelta
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import HTTPException, status
from cryptography.fernet import Fernet, InvalidToken
from sqlmodel import Session, select

from backend.app.core.config import Settings
from backend.app.db.models import AuthSession, Invitation, OAuthState, User, Workspace, utc_now


GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
IDENTITY_SCOPES = ("openid", "email", "profile")


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str
    email: str
    email_verified: bool
    display_name: str
    avatar_url: str | None = None


class GoogleOAuthClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def authorization_url(self, *, state: str, verifier: str, redirect_uri: str, scopes: tuple[str, ...] = IDENTITY_SCOPES) -> str:
        if not self.settings.google_oauth_client_id:
            raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
        query = urlencode(
            {
                "client_id": self.settings.google_oauth_client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(scopes),
                "state": state,
                "code_challenge": _pkce_challenge(verifier),
                "code_challenge_method": "S256",
                "access_type": "offline",
                "include_granted_scopes": "true",
                "prompt": "select_account",
            }
        )
        return f"{GOOGLE_AUTHORIZE_URL}?{query}"

    def exchange_identity(self, *, code: str, verifier: str, redirect_uri: str) -> GoogleIdentity:
        identity, _credentials_json = self.exchange_credentials(
            code=code,
            verifier=verifier,
            redirect_uri=redirect_uri,
            scopes=IDENTITY_SCOPES,
        )
        return identity

    def exchange_credentials(
        self,
        *,
        code: str,
        verifier: str,
        redirect_uri: str,
        scopes: tuple[str, ...],
    ) -> tuple[GoogleIdentity, str]:
        if not self.settings.google_oauth_client_id or not self.settings.google_oauth_client_secret:
            raise HTTPException(status_code=503, detail="Google sign-in is not configured.")
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.id_token import verify_oauth2_token
            from google_auth_oauthlib.flow import Flow

            flow = Flow.from_client_config(
                {
                    "web": {
                        "client_id": self.settings.google_oauth_client_id,
                        "client_secret": self.settings.google_oauth_client_secret,
                        "auth_uri": GOOGLE_AUTHORIZE_URL,
                        "token_uri": "https://oauth2.googleapis.com/token",
                    }
                },
                scopes=list(scopes),
                state=None,
                redirect_uri=redirect_uri,
                code_verifier=verifier,
            )
            flow.fetch_token(code=code)
            claims = verify_oauth2_token(
                flow.credentials.id_token,
                Request(),
                audience=self.settings.google_oauth_client_id,
            )
        except Exception as exc:
            raise HTTPException(status_code=401, detail="Google sign-in could not be verified.") from exc
        identity = GoogleIdentity(
            subject=str(claims["sub"]),
            email=str(claims["email"]).strip().lower(),
            email_verified=bool(claims.get("email_verified")),
            display_name=str(claims.get("name") or claims["email"]),
            avatar_url=str(claims["picture"]) if claims.get("picture") else None,
        )
        return identity, flow.credentials.to_json()


class AuthService:
    def __init__(self, session: Session, settings: Settings) -> None:
        self.session = session
        self.settings = settings

    def start_oauth(
        self,
        purpose: str = "login",
        user_id: int | None = None,
        *,
        callback_path: str = "/auth/google/callback",
        scopes: tuple[str, ...] = IDENTITY_SCOPES,
    ) -> tuple[str, str]:
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        redirect_uri = f"{self.settings.public_base_url.rstrip('/')}{callback_path}"
        self.session.add(
            OAuthState(
                state_hash=token_hash(state),
                purpose=purpose,
                user_id=user_id,
                code_verifier=verifier,
                redirect_uri=redirect_uri,
                expires_at=utc_now() + timedelta(minutes=10),
            )
        )
        self.session.commit()
        url = GoogleOAuthClient(self.settings).authorization_url(
            state=state,
            verifier=verifier,
            redirect_uri=redirect_uri,
            scopes=scopes,
        )
        return state, url

    def consume_state(self, raw_state: str, purpose: str = "login") -> OAuthState:
        record = self.session.exec(select(OAuthState).where(OAuthState.state_hash == token_hash(raw_state))).first()
        if (
            record is None
            or record.purpose != purpose
            or record.consumed_at is not None
            or record.expires_at <= utc_now()
        ):
            raise HTTPException(status_code=401, detail="The sign-in request expired or is invalid.")
        record.consumed_at = utc_now()
        self.session.add(record)
        self.session.commit()
        self.session.refresh(record)
        return record

    def authenticate_google_identity(self, identity: GoogleIdentity) -> User:
        if not identity.email_verified:
            raise HTTPException(status_code=403, detail="A verified Google email is required.")
        existing = self.session.exec(select(User).where(User.google_subject == identity.subject)).first()
        if existing is not None:
            if existing.status != "active":
                raise HTTPException(status_code=403, detail="This account is not active.")
            existing.email = identity.email
            existing.display_name = identity.display_name
            existing.avatar_url = identity.avatar_url
            existing.last_login_at = utc_now()
            existing.updated_at = utc_now()
            self.session.add(existing)
            self.session.commit()
            self.session.refresh(existing)
            return existing

        invitation = self.session.exec(select(Invitation).where(Invitation.email == identity.email)).first()
        is_bootstrap = bool(
            self.settings.bootstrap_admin_email
            and hmac.compare_digest(identity.email, self.settings.bootstrap_admin_email.strip().lower())
        )
        if (invitation is None or invitation.status != "pending") and not is_bootstrap:
            raise HTTPException(status_code=403, detail="This app is invite-only.")

        user = User(
            google_subject=identity.subject,
            email=identity.email,
            display_name=identity.display_name,
            avatar_url=identity.avatar_url,
            role="admin" if is_bootstrap else invitation.role,
            status="active",
            last_login_at=utc_now(),
        )
        self.session.add(user)
        self.session.flush()

        legacy_user = self.session.exec(select(User).where(User.google_subject == "bootstrap:legacy")).first()
        legacy_workspace = (
            self.session.exec(select(Workspace).where(Workspace.owner_user_id == legacy_user.id)).first()
            if legacy_user is not None and is_bootstrap
            else None
        )
        if legacy_workspace is not None:
            legacy_workspace.owner_user_id = user.id
            legacy_workspace.name = f"{identity.display_name}'s workspace"
            legacy_workspace.updated_at = utc_now()
            self.session.add(legacy_workspace)
            legacy_user.status = "superseded"
            legacy_user.updated_at = utc_now()
            legacy_user.email = f"legacy-{legacy_user.id}@local.invalid"
            self.session.add(legacy_user)
        else:
            self.session.add(
                Workspace(
                    workspace_id=f"workspace-{uuid4()}",
                    owner_user_id=user.id,
                    name=f"{identity.display_name}'s workspace",
                )
            )
        if invitation is not None:
            invitation.status = "accepted"
            invitation.accepted_by_user_id = user.id
            invitation.accepted_at = utc_now()
            self.session.add(invitation)
        self.session.commit()
        self.session.refresh(user)
        return user

    def create_session(self, user: User) -> str:
        raw_token = secrets.token_urlsafe(48)
        self.session.add(
            AuthSession(
                session_id=f"session-{uuid4()}",
                token_hash=token_hash(raw_token),
                user_id=user.id,
                expires_at=utc_now() + timedelta(days=self.settings.auth_session_days),
            )
        )
        self.session.commit()
        return raw_token

    def revoke_session(self, raw_token: str | None) -> None:
        if not raw_token:
            return
        record = self.session.exec(select(AuthSession).where(AuthSession.token_hash == token_hash(raw_token))).first()
        if record is not None:
            record.revoked_at = utc_now()
            self.session.add(record)
            self.session.commit()


def csrf_token(session_token: str, settings: Settings) -> str:
    secret = settings.credential_encryption_key or settings.google_oauth_client_secret or "local-development-only"
    return hmac.new(secret.encode("utf-8"), session_token.encode("utf-8"), hashlib.sha256).hexdigest()


class CredentialVault:
    def __init__(self, settings: Settings) -> None:
        if not settings.credential_encryption_key:
            raise HTTPException(status_code=503, detail="Credential encryption is not configured.")
        digest = hashlib.sha256(settings.credential_encryption_key.encode("utf-8")).digest()
        self._fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self._fernet.encrypt(value.encode("utf-8")).decode("ascii")

    def decrypt(self, value: str) -> str:
        try:
            return self._fernet.decrypt(value.encode("ascii")).decode("utf-8")
        except InvalidToken as exc:
            raise HTTPException(status_code=503, detail="Stored Gmail credentials cannot be decrypted.") from exc


def require_role(user: User, role: str) -> None:
    if user.role != role:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Administrator access is required.")
