from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from fastapi import Request
from sqlmodel import Session

from backend.app.db.models import Workspace


DEFAULT_LOCALE: Final = "en"


@dataclass(frozen=True)
class LocaleDefinition:
    locale: str
    display_name: str
    fallback_locale: str
    agent_language: str
    address_style: str


LOCALE_REGISTRY: Final = {
    "en": LocaleDefinition("en", "English", "en", "English", "professional and direct"),
    "de-DE": LocaleDefinition("de-DE", "Deutsch", "en", "German for Germany", "professional Du"),
}
SUPPORTED_LOCALES: Final = tuple(LOCALE_REGISTRY)


def normalize_locale(value: str | None) -> str:
    normalized = (value or "").strip().replace("_", "-").lower()
    if normalized == "de" or normalized.startswith("de-"):
        return "de-DE"
    return DEFAULT_LOCALE


def workspace_locale(session: Session, workspace_id: int | None) -> str:
    workspace = session.get(Workspace, workspace_id) if workspace_id is not None else None
    return normalize_locale(workspace.locale if workspace is not None else None)


def request_locale(request: Request, session: Session | None = None) -> str:
    workspace_id = getattr(request.state, "workspace_id", None)
    if session is not None and workspace_id is not None:
        return workspace_locale(session, workspace_id)
    cookie_locale = request.cookies.get("ai_locale")
    if cookie_locale:
        return normalize_locale(cookie_locale)
    return normalize_locale(request.headers.get("accept-language"))


def output_language_contract(locale: str) -> str:
    definition = LOCALE_REGISTRY[normalize_locale(locale)]
    return (
        "You may reason and use tools in English when that improves quality. "
        f"All newly generated user-visible replies, summaries, descriptions, fit reasons, risks, "
        f"review explanations, and recommendations must be idiomatic {definition.agent_language} "
        f"({definition.locale}), using a {definition.address_style} tone. Preserve user-authored "
        "text, proper names, quotations, vacancy text, and external source material in their original "
        "language. JSON keys, stable IDs, status codes, review flags, and provenance identifiers remain "
        "in their defined form."
    )


def localized_text(locale: str, english: str, german: str) -> str:
    return german if normalize_locale(locale) == "de-DE" else english


def default_workspace_name(display_name: str, locale: str) -> str:
    return localized_text(locale, f"{display_name}'s workspace", f"Workspace von {display_name}")
