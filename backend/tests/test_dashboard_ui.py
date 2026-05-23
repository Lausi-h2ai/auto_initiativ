from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


class _DashboardAssetParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.scripts: list[str] = []
        self.stylesheets: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script" and attributes.get("src"):
            self.scripts.append(attributes["src"] or "")
        rel_values = set((attributes.get("rel") or "").split())
        if tag == "link" and "stylesheet" in rel_values and attributes.get("href"):
            self.stylesheets.append(attributes["href"] or "")


def _dashboard_assets(client) -> tuple[str, dict[str, str]]:
    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

    html = response.text
    assert "<html" in html.lower()
    assert "dashboard" in html.lower()

    parser = _DashboardAssetParser()
    parser.feed(html)

    assert parser.scripts
    assert parser.stylesheets

    assets: dict[str, str] = {}
    for asset_path in parser.scripts + parser.stylesheets:
        asset_url = urljoin("/dashboard", asset_path)
        asset_response = client.get(asset_url)

        assert asset_response.status_code == 200
        assets[asset_url] = asset_response.text

    return html, assets


def test_dashboard_returns_html_for_actual_app(client):
    html, assets = _dashboard_assets(client)

    combined = "\n".join([html, *assets.values()]).lower()

    assert "dashboard" in combined
    assert "/dashboard/summary" in combined


def test_dashboard_static_js_and_css_are_served(client):
    _, assets = _dashboard_assets(client)

    js_assets = {path: body for path, body in assets.items() if urlparse(path).path.endswith(".js")}
    css_assets = {path: body for path, body in assets.items() if urlparse(path).path.endswith(".css")}

    assert js_assets
    assert css_assets
    assert all("javascript" in client.get(path).headers["content-type"] for path in js_assets)
    assert all("text/css" in client.get(path).headers["content-type"] for path in css_assets)


def test_dashboard_assets_reference_required_read_only_api_endpoints(client):
    html, assets = _dashboard_assets(client)
    combined = "\n".join([html, *assets.values()])

    required_endpoints = {
        "/dashboard/summary",
        "/profile/summary",
        "/campaigns/company-research",
        "/runs",
        "/onboarding/chat/",
        "/onboarding/runs/",
        "/artifacts",
        "/input-files",
        "/import-artifacts",
        "/promote",
        "/companies",
        "/contacts",
        "/fit-evaluations",
        "/email-drafts",
        "/send-intents",
        "/gate-results",
        "/outreach-records",
        "/audit-logs",
    }

    for endpoint in required_endpoints:
        assert endpoint in combined

    required_product_text = {
        "Profile Setup",
        "Start profile interview",
        "Waiting for profile agent reply",
        "Finish artifacts",
        "Finalizing candidate profile artifacts",
        "Upload resume",
        "Validate artifacts",
        "Candidate artifacts",
        "Approve reviewed profile",
        "Review each JSON artifact",
        "Prepare company research run",
        "Generated files and transcript",
        "user_profile.json",
        "master_cv_profile.json",
        "policy.json",
        "onboarding_review.json",
        "No approved profile yet",
        "Local profile mode",
        "Developer logs",
    }
    for text in required_product_text:
        assert text in combined

    assert "Start Onboarding" not in combined
    assert 'label: "Onboarding"' not in combined


def test_dashboard_assets_do_not_expose_sending_or_external_ai_surfaces(client):
    html, assets = _dashboard_assets(client)
    combined = "\n".join([html, *assets.values()]).lower()

    forbidden_terms = {
        "gmail",
        "openai",
        "email adapter",
        "send adapter",
        "reservation",
        "reserve for send",
        "send now",
        "send email",
        "approve send",
    }
    for term in forbidden_terms:
        assert term not in combined

    forbidden_endpoint_patterns = [
        r"['\"]\/send(?:['\"/?#]|\b)",
        r"['\"][^'\"]*\/send-reservations(?:['\"/?#]|\b)",
        r"['\"][^'\"]*\/dashboard\/send-reservations(?:['\"/?#]|\b)",
        r"['\"][^'\"]*\/gate\/evaluations\/",
    ]
    for pattern in forbidden_endpoint_patterns:
        assert re.search(pattern, combined) is None
