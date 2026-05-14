from __future__ import annotations

import re
from urllib.parse import urlsplit


_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_WHITESPACE_RE = re.compile(r"\s+")


def normalize_recipient_email(value: str) -> str:
    normalized = value.strip().lower()
    if not _EMAIL_RE.fullmatch(normalized):
        raise ValueError("Invalid recipient email syntax.")
    return normalized


def normalize_company_domain(value: str | None) -> str | None:
    if value is None:
        return None

    raw = value.strip()
    if not raw:
        return None

    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    host = parsed.hostname or raw.split("/", 1)[0].split("?", 1)[0].split("#", 1)[0]
    host = host.strip().lower().rstrip(".")

    if host.startswith("www."):
        host = host[4:]

    if not host or any(char.isspace() for char in host):
        raise ValueError("Invalid company domain.")

    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as exc:
        raise ValueError("Invalid company domain.") from exc

    if "." not in host or host.startswith(".") or host.endswith("."):
        raise ValueError("Invalid company domain.")

    return host


def normalize_company_name(value: str) -> str:
    normalized = _WHITESPACE_RE.sub(" ", value.strip()).casefold()
    if not normalized:
        raise ValueError("Company name is required.")
    return normalized


def build_company_policy_key(*, normalized_domain: str | None, normalized_name: str) -> tuple[str, str]:
    if normalized_domain:
        return f"domain:{normalized_domain}", "domain"
    return f"name:{normalize_company_name(normalized_name)}", "name"
