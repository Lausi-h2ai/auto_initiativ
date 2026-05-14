from __future__ import annotations

import pytest

from backend.app.db.normalization import (
    build_company_policy_key,
    normalize_company_domain,
    normalize_company_name,
    normalize_recipient_email,
)


def test_recipient_email_normalization_trims_and_lowercases():
    assert normalize_recipient_email(" Hiring.Lead@Example.COM ") == "hiring.lead@example.com"


def test_recipient_email_normalization_rejects_invalid_syntax():
    with pytest.raises(ValueError, match="Invalid recipient email"):
        normalize_recipient_email("not an address")


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (" HTTPS://WWW.Example.COM:443/careers?ref=x#jobs ", "example.com"),
        ("www.Example.com.", "example.com"),
        ("bücher.example/jobs", "xn--bcher-kva.example"),
    ],
)
def test_company_domain_normalization(raw, expected):
    assert normalize_company_domain(raw) == expected


@pytest.mark.parametrize("raw", ["", "example", "bad domain.com"])
def test_company_domain_normalization_rejects_missing_or_invalid_domains(raw):
    if raw == "":
        assert normalize_company_domain(raw) is None
        return

    with pytest.raises(ValueError, match="Invalid company domain"):
        normalize_company_domain(raw)


def test_company_name_normalization_collapses_whitespace_and_casefolds():
    assert normalize_company_name("  Example   GmbH  ") == "example gmbh"


def test_company_policy_key_prefers_domain():
    assert build_company_policy_key(normalized_domain="example.com", normalized_name="Example GmbH") == (
        "domain:example.com",
        "domain",
    )


def test_company_policy_key_uses_name_fallback():
    assert build_company_policy_key(normalized_domain=None, normalized_name="  Example   GmbH  ") == (
        "name:example gmbh",
        "name",
    )
