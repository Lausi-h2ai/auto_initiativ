from __future__ import annotations

from dataclasses import dataclass, field
from email.message import EmailMessage as MimeEmailMessage
from email.utils import make_msgid
import base64
from pathlib import Path
from typing import Any, Protocol

from backend.app.core.config import Settings


@dataclass(frozen=True)
class EmailMessage:
    intent_id: str
    recipient_email: str
    subject: str
    body_text: str
    body_html: str | None = None
    attachments: list[dict[str, Any]] = field(default_factory=list)
    headers: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class EmailDeliveryResult:
    provider: str
    status: str
    intent_id: str
    recipient_email: str
    provider_message_id: str | None = None
    provider_thread_id: str | None = None
    network_performed: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


class EmailAdapter(Protocol):
    provider: str

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        """Perform an adapter handoff.

        Real adapters are intentionally not implemented in this phase. The fake
        adapter records only an in-memory dry-run result and never performs I/O.
        """


class GmailPreSendError(RuntimeError):
    """Raised when Gmail setup/auth fails before the send API call is made."""


class GmailProviderRejectedBeforeAcceptError(RuntimeError):
    """Raised when Gmail rejects the send request without accepting a message."""


class FakeDryRunEmailAdapter:
    provider = "fake_dry_run"

    def __init__(self) -> None:
        self.messages: list[EmailMessage] = []

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        self.messages.append(message)
        return EmailDeliveryResult(
            provider=self.provider,
            status="dry_run_recorded",
            intent_id=message.intent_id,
            recipient_email=message.recipient_email,
            provider_message_id=f"fake-dry-run-{message.intent_id}",
            provider_thread_id=None,
            network_performed=False,
            metadata={"message_count": len(self.messages)},
        )


class GmailEmailAdapter:
    provider = "gmail"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, message: EmailMessage) -> EmailDeliveryResult:
        service = self._service()
        payload = {"raw": _message_to_gmail_raw(message)}
        try:
            response = service.users().messages().send(userId=self.settings.gmail_user_id, body=payload).execute()
        except Exception as exc:
            status = getattr(getattr(exc, "resp", None), "status", None)
            if isinstance(status, str) and status.isdigit():
                status = int(status)
            if isinstance(status, int) and 400 <= status < 500:
                raise GmailProviderRejectedBeforeAcceptError(f"Gmail rejected before accepting message: {exc}") from exc
            raise
        return EmailDeliveryResult(
            provider=self.provider,
            status="provider_accepted",
            intent_id=message.intent_id,
            recipient_email=message.recipient_email,
            provider_message_id=response.get("id"),
            provider_thread_id=response.get("threadId"),
            network_performed=True,
            metadata={"response": response},
        )

    def _service(self) -> Any:
        if self.settings.gmail_oauth_client_secrets_path is None or self.settings.gmail_oauth_token_path is None:
            raise GmailPreSendError("Gmail OAuth paths are not configured.")

        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build

            token_path = self.settings.gmail_oauth_token_path
            scopes = self.settings.gmail_oauth_scopes
            credentials = None
            if token_path.exists():
                credentials = Credentials.from_authorized_user_file(str(token_path), scopes)
            if credentials is None or not credentials.valid:
                if credentials is not None and credentials.expired and credentials.refresh_token:
                    try:
                        credentials.refresh(Request())
                    except Exception:
                        credentials = None
                if credentials is None or not credentials.valid:
                    flow = InstalledAppFlow.from_client_secrets_file(str(self.settings.gmail_oauth_client_secrets_path), scopes)
                    credentials = flow.run_local_server(port=0)
                token_path.parent.mkdir(parents=True, exist_ok=True)
                token_path.write_text(credentials.to_json(), encoding="utf-8")
            return build("gmail", "v1", credentials=credentials)
        except GmailPreSendError:
            raise
        except Exception as exc:
            raise GmailPreSendError(f"Gmail setup/auth failed before send: {exc}") from exc


def _message_to_gmail_raw(message: EmailMessage) -> str:
    mime = MimeEmailMessage()
    mime["To"] = message.recipient_email
    mime["Subject"] = message.subject
    mime["Message-ID"] = make_msgid(idstring=message.intent_id)
    for key, value in sorted(message.headers.items()):
        mime[key] = value
    if message.body_html:
        mime.set_content(message.body_text)
        mime.add_alternative(message.body_html, subtype="html")
    else:
        mime.set_content(message.body_text)

    for attachment in message.attachments:
        path_value = attachment.get("resolved_path") or attachment.get("path")
        if not isinstance(path_value, str) or not path_value:
            continue
        path = Path(path_value)
        if not path.is_file():
            continue
        data = path.read_bytes()
        maintype, subtype = _attachment_mime_type(path)
        mime.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)

    return base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")


def _attachment_mime_type(path: Path) -> tuple[str, str]:
    if path.suffix.lower() == ".pdf":
        return "application", "pdf"
    if path.suffix.lower() in {".html", ".htm"}:
        return "text", "html"
    if path.suffix.lower() == ".txt":
        return "text", "plain"
    return "application", "octet-stream"
